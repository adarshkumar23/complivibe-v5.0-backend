import hashlib
import re
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.url_security import UnsafeURLTargetError, assert_public_http_url
from app.models.compliance_report import ComplianceReport
from app.models.export_job import ExportJob
from app.repositories.report_repository import ReportRepository
from app.schemas.reports import XBRLExportRequest
from app.services.export_service import ExportService

CONCEPT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*:[A-Za-z_][A-Za-z0-9_.-]*$")
PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
NUMERIC_UNITS = {"iso4217:USD", "iso4217:EUR", "iso4217:GBP", "shares", "pure", "tCO2e", "MWh", "GJ"}
TAXONOMY_SOURCE_ERROR_CODES = {"FileNotLoadable", "IOError", "webCache:retrievalError"}


class TaxonomySourceUnavailableError(RuntimeError):
    pass


class TaxonomySourceRejectedError(RuntimeError):
    pass


class XBRLValidationFailedError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(", ".join(errors))


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise TaxonomySourceRejectedError("taxonomy_schema_url redirects are not allowed")


class XBRLExportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def _report_or_404(self, org_id: uuid.UUID, report_id: uuid.UUID) -> ComplianceReport:
        report = ReportRepository(self.db).get_report(report_id)
        if report is None or report.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        return report

    @staticmethod
    def _validation_errors(payload: XBRLExportRequest) -> list[dict]:
        errors: list[dict] = []
        if not PREFIX_RE.match(payload.taxonomy_prefix):
            errors.append({"data_point_index": None, "field": "taxonomy_prefix", "message": "Taxonomy prefix must be an XML-safe prefix."})

        for index, point in enumerate(payload.data_points):
            if not CONCEPT_RE.match(point.taxonomy_concept):
                errors.append(
                    {
                        "data_point_index": index,
                        "field": "taxonomy_concept",
                        "message": "Taxonomy concept must use a prefix-qualified name such as issb:ClimateRelatedRisks.",
                    }
                )
            if point.instant is None and (point.period_start is None or point.period_end is None):
                errors.append(
                    {
                        "data_point_index": index,
                        "field": "period",
                        "message": "Provide either instant or both period_start and period_end.",
                    }
                )
            if point.instant is not None and (point.period_start is not None or point.period_end is not None):
                errors.append(
                    {
                        "data_point_index": index,
                        "field": "period",
                        "message": "Use instant or duration dates, not both.",
                    }
                )
            if point.period_start is not None and point.period_end is not None and point.period_end < point.period_start:
                errors.append({"data_point_index": index, "field": "period_end", "message": "period_end must be on or after period_start."})
            if isinstance(point.value, (int, float)) and not point.unit:
                errors.append({"data_point_index": index, "field": "unit", "message": "Numeric data points require a unit."})
            if point.unit and point.unit not in NUMERIC_UNITS and ":" not in point.unit:
                errors.append(
                    {
                        "data_point_index": index,
                        "field": "unit",
                        "message": "Unit must be a recognized ESG unit or a prefix-qualified unit.",
                    }
                )
        return errors

    @staticmethod
    def _date(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.date().isoformat()

    def _build_xbrl(self, report: ComplianceReport, payload: XBRLExportRequest) -> str:
        ET.register_namespace("xbrli", "http://www.xbrl.org/2003/instance")
        ET.register_namespace("link", "http://www.xbrl.org/2003/linkbase")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        ET.register_namespace(payload.taxonomy_prefix, payload.taxonomy_namespace)

        root = ET.Element("{http://www.xbrl.org/2003/instance}xbrl")
        ET.SubElement(
            root,
            "{http://www.xbrl.org/2003/linkbase}schemaRef",
            {
                "{http://www.w3.org/1999/xlink}type": "simple",
                "{http://www.w3.org/1999/xlink}href": payload.taxonomy_schema_url,
            },
        )

        unit_ids: dict[str, str] = {}
        for index, point in enumerate(payload.data_points):
            context_id = f"c{index + 1}"
            context = ET.SubElement(root, "{http://www.xbrl.org/2003/instance}context", {"id": context_id})
            entity = ET.SubElement(context, "{http://www.xbrl.org/2003/instance}entity")
            ET.SubElement(entity, "{http://www.xbrl.org/2003/instance}identifier", {"scheme": "https://complivibe.local/organizations"}).text = (
                payload.entity_identifier
            )
            period = ET.SubElement(context, "{http://www.xbrl.org/2003/instance}period")
            if point.instant is not None:
                ET.SubElement(period, "{http://www.xbrl.org/2003/instance}instant").text = self._date(point.instant)
            else:
                ET.SubElement(period, "{http://www.xbrl.org/2003/instance}startDate").text = self._date(point.period_start)  # type: ignore[arg-type]
                ET.SubElement(period, "{http://www.xbrl.org/2003/instance}endDate").text = self._date(point.period_end)  # type: ignore[arg-type]

            _, local_name = point.taxonomy_concept.split(":", 1)
            attrs = {"contextRef": context_id}
            if point.unit:
                unit_id = unit_ids.setdefault(point.unit, f"u{len(unit_ids) + 1}")
                attrs["unitRef"] = unit_id
                attrs["decimals"] = str(point.decimals if point.decimals is not None else 0)
            ET.SubElement(root, f"{{{payload.taxonomy_namespace}}}{local_name}", attrs).text = str(point.value)

        for unit_name, unit_id in unit_ids.items():
            unit = ET.SubElement(root, "{http://www.xbrl.org/2003/instance}unit", {"id": unit_id})
            ET.SubElement(unit, "{http://www.xbrl.org/2003/instance}measure").text = unit_name

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _reject_if_internal_target(taxonomy_schema_url: str) -> None:
        """Block SSRF: the taxonomy schema URL is caller-supplied and the server fetches it
        directly, so refuse anything that doesn't resolve to a public host/scheme."""
        try:
            assert_public_http_url(taxonomy_schema_url, field_name="taxonomy_schema_url")
        except UnsafeURLTargetError as exc:
            raise TaxonomySourceRejectedError(str(exc)) from exc

    @staticmethod
    def _check_taxonomy_source(taxonomy_schema_url: str) -> None:
        XBRLExportService._reject_if_internal_target(taxonomy_schema_url)
        opener = urllib.request.build_opener(_NoRedirectHandler)
        request = urllib.request.Request(taxonomy_schema_url, method="HEAD")
        try:
            with opener.open(request, timeout=15) as response:
                if response.status >= 400:
                    raise TaxonomySourceUnavailableError("taxonomy source returned an error status")
        except urllib.error.HTTPError as exc:
            if exc.code == 405:
                get_request = urllib.request.Request(taxonomy_schema_url, method="GET", headers={"Range": "bytes=0-0"})
                try:
                    with opener.open(get_request, timeout=15) as response:
                        if response.status >= 400:
                            raise TaxonomySourceUnavailableError("taxonomy source returned an error status") from exc
                except (OSError, TimeoutError, urllib.error.URLError) as nested_exc:
                    raise TaxonomySourceUnavailableError("taxonomy source unreachable") from nested_exc
                return
            raise TaxonomySourceUnavailableError("taxonomy source returned an error status") from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise TaxonomySourceUnavailableError("taxonomy source unreachable") from exc

    @staticmethod
    def _engine_parse_check(xbrl_content: str, taxonomy_schema_url: str) -> None:
        # Keep the engine invocation internal; API responses must stay vendor-neutral.
        from arelle import Cntlr, ModelManager  # type: ignore[import-not-found]

        XBRLExportService._check_taxonomy_source(taxonomy_schema_url)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.xbrl"
            log_path = Path(tmpdir) / "arelle.log"
            path.write_text(xbrl_content, encoding="utf-8")
            controller = Cntlr.Cntlr(logFileName=str(log_path))
            model_manager = ModelManager.initialize(controller)
            model_xbrl = model_manager.load(str(path))
            if model_xbrl is None:
                raise ValueError("XBRL parser could not read generated document")
            errors = [str(error) for error in (getattr(model_xbrl, "errors", None) or [])]
            model_xbrl.close()
            if any(error in TAXONOMY_SOURCE_ERROR_CODES for error in errors):
                raise TaxonomySourceUnavailableError("taxonomy source unreachable")
            if errors:
                raise XBRLValidationFailedError(errors)

    def export_report(
        self,
        *,
        org_id: uuid.UUID,
        report_id: uuid.UUID,
        payload: XBRLExportRequest,
        requested_by_user_id: uuid.UUID,
    ) -> tuple[ExportJob, str, str, str]:
        report = self._report_or_404(org_id, report_id)
        validation_errors = self._validation_errors(payload)
        if validation_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "XBRL validation failed", "validation_errors": validation_errors},
            )

        xbrl_content = self._build_xbrl(report, payload)
        try:
            self._engine_parse_check(xbrl_content, payload.taxonomy_schema_url)
        except TaxonomySourceRejectedError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "XBRL validation failed",
                    "validation_errors": [
                        {
                            "data_point_index": None,
                            "field": "taxonomy_schema_url",
                            "message": "taxonomy_schema_url must be a public http(s) URL; internal or private addresses are not allowed.",
                        }
                    ],
                },
            ) from exc
        except TaxonomySourceUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "XBRL taxonomy source unreachable",
                    "taxonomy_schema_url": payload.taxonomy_schema_url,
                },
            ) from exc
        except XBRLValidationFailedError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "XBRL validation failed",
                    "validation_errors": [{"data_point_index": None, "field": "document", "message": "Generated XBRL failed taxonomy validation."}],
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "XBRL validation failed",
                    "validation_errors": [{"data_point_index": None, "field": "document", "message": "Generated XBRL could not be validated."}],
                },
            ) from exc

        content_bytes = xbrl_content.encode("utf-8")
        checksum = hashlib.sha256(content_bytes).hexdigest()
        storage_root = Path(get_settings().FILE_STORAGE_PATH or "/tmp/complivibe_exports/").expanduser()
        export_dir = storage_root / "reports" / str(org_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(export_dir / f"{report.id}_{self.now().strftime('%Y%m%d%H%M%S')}.xbrl")
        Path(file_path).write_bytes(content_bytes)

        job = ExportService(self.db).create_completed_binary_export_job(
            organization_id=org_id,
            source_report_id=report.id,
            export_type="compliance_report_xbrl",
            title="Compliance Report XBRL Export",
            description="Generated XBRL export for compliance report",
            file_path=file_path,
            file_format="xbrl",
            file_size_bytes=len(content_bytes),
            checksum_sha256=checksum,
            requested_by_user_id=requested_by_user_id,
        )
        return job, xbrl_content, checksum, file_path
