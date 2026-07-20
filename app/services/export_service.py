import hashlib
import hmac
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection
from app.models.control import Control
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.export_job import ExportJob
from app.models.export_job_event import ExportJobEvent
from app.models.framework import Framework
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.risk_evidence_link import RiskEvidenceLink
from app.models.score_snapshot import ScoreSnapshot
from app.models.task import Task
from app.repositories.export_repository import ExportRepository
from app.repositories.report_repository import ReportRepository
from app.services.evidence_service import EvidenceService
from app.services.report_service import REPORT_CAVEAT, ReportService
from app.services.risk_service import RiskService
from app.services.task_service import TaskService
from app.core.validation import validate_choice

ALLOWED_EXPORT_TYPES = {
    "compliance_report_json",
    "framework_readiness_json",
    "evidence_manifest_json",
    "risk_register_json",
    "task_execution_json",
    "executive_summary_json",
    "audit_preparation_json",
    "compliance_report_pdf",
    "compliance_report_docx",
    "compliance_report_xbrl",
}

INTEGRITY_ALGORITHM = "HMAC-SHA256"
SIGNING_KEY_ID = "app-default-hmac-v1"
PACKAGE_VERSION = "1.0"

# Every signed export gets a validity window; the default is one year and a caller may
# request a SHORTER one at export time (a longer request is clamped down to the default).
DEFAULT_VALIDITY_DAYS = 365
MAX_VALIDITY_DAYS = 365


def signing_secret_for_key_id(key_id: str | None) -> bytes:
    """Resolve the HMAC secret for a recorded signing_key_id.

    This is the extension point for key rotation and the reason verify now CONSULTS the
    recorded key-id instead of always recomputing from a hardcoded constant: a future
    rotation registers new key-ids here while retaining older ones, so historical exports
    keep verifying rather than being invalidated by a code change. Today every key-id --
    the default SIGNING_KEY_ID and legacy NULL alike -- maps to SECRET_KEY.

    LIMITATION: this does NOT make rotation of SECRET_KEY itself safe. HMAC is symmetric,
    so signatures produced under an old SECRET_KEY verify only while that old key is still
    returned here for its key-id; rotating SECRET_KEY without retaining the old value for
    verification would invalidate everything signed under it. That is an inherent property
    of staying on symmetric HMAC, not a defect in this fix.
    """
    _ = key_id
    return get_settings().SECRET_KEY.encode("utf-8")

EXPORT_CAVEAT = (
    "This export is generated from CompliVibe system records. It is not a legal opinion, "
    "regulatory approval, audit certification, or proof of compliance by itself."
)


class ExportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ExportRepository(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def validate_export_type(export_type: str) -> None:
        export_type = validate_choice(export_type, ALLOWED_EXPORT_TYPES, "export_type", status_code=status.HTTP_400_BAD_REQUEST)

    def validate_period_window(self, period_start: datetime | None, period_end: datetime | None) -> None:
        if period_start and period_end and period_end < period_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period_end must be greater than or equal to period_start",
            )

    def job_context(self, row: ExportJob) -> dict[str, Any]:
        now = self.now()
        created_at = self.as_utc(row.created_at) or now
        started_at = self.as_utc(row.started_at)
        age_days = max(0, (now.date() - created_at.date()).days)
        is_terminal = row.status in {"completed", "failed", "cancelled", "archived"}
        is_integrity_bound = bool(row.checksum_sha256 and row.integrity_signature and row.signature_algorithm)

        flags: list[str] = [f"export_{row.status}"]
        if row.status == "queued" and (now - created_at) > timedelta(hours=24):
            flags.append("queued_too_long")
        if row.status == "processing" and started_at and (now - started_at) > timedelta(hours=2):
            flags.append("processing_too_long")
        if row.status == "completed" and not is_integrity_bound:
            flags.append("integrity_artifacts_missing")
        if row.status == "completed" and not row.immutable_after_completion:
            flags.append("immutability_disabled")
        if row.legal_hold:
            flags.append("legal_hold_enabled")
        if row.locked_until and self.as_utc(row.locked_until) and self.as_utc(row.locked_until) > now:
            flags.append("retention_lock_active")
        if row.period_start and row.period_end and row.period_end < row.period_start:
            flags.append("invalid_period_range")
        if row.export_type == "compliance_report_json" and row.source_report_id is None:
            flags.append("missing_source_report")
        if row.export_type == "framework_readiness_json" and row.framework_id is None:
            flags.append("missing_framework_id")

        return {
            "age_days": age_days,
            "is_terminal": is_terminal,
            "is_integrity_bound": is_integrity_bound,
            "context_flags": flags,
        }

    def job_response_payload(self, row: ExportJob) -> dict[str, Any]:
        context = self.job_context(row)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "export_type": row.export_type,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "requested_by_user_id": row.requested_by_user_id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "failed_at": row.failed_at,
            "cancelled_at": row.cancelled_at,
            "archived_at": row.archived_at,
            "error_message": row.error_message,
            "source_report_id": row.source_report_id,
            "framework_id": row.framework_id,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "checksum_sha256": row.checksum_sha256,
            "integrity_signature": row.integrity_signature,
            "signing_key_id": row.signing_key_id,
            "signature_algorithm": row.signature_algorithm,
            "locked_until": row.locked_until,
            "retention_until": row.retention_until,
            "legal_hold": row.legal_hold,
            "legal_hold_reason": row.legal_hold_reason,
            "legal_hold_set_by_user_id": row.legal_hold_set_by_user_id,
            "legal_hold_set_at": row.legal_hold_set_at,
            "attestation_status": row.attestation_status,
            "latest_attestation_id": row.latest_attestation_id,
            "package_version": row.package_version,
            "immutable_after_completion": row.immutable_after_completion,
            "metadata_json": row.metadata_json,
            "age_days": context["age_days"],
            "is_terminal": context["is_terminal"],
            "is_integrity_bound": context["is_integrity_bound"],
            "context_flags": context["context_flags"],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _canonical_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _checksum_payload(self, package_json: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(package_json)
        manifest = payload.get("manifest") or {}
        manifest["package_checksum_sha256"] = None
        payload["manifest"] = manifest
        return payload

    def compute_checksum(self, package_json: dict[str, Any]) -> str:
        canonical = self._canonical_json(self._checksum_payload(package_json)).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def validity_window(self, validity_days: int | None = None) -> tuple[datetime, datetime]:
        """(valid_from, not_after) for a new signature. Default one year; a caller may
        request a shorter window, but never a longer one."""
        valid_from = self.now()
        days = DEFAULT_VALIDITY_DAYS if validity_days is None else max(1, min(int(validity_days), MAX_VALIDITY_DAYS))
        return valid_from, valid_from + timedelta(days=days)

    def compute_integrity_signature(
        self,
        checksum_sha256: str,
        *,
        valid_from: datetime | None = None,
        not_after: datetime | None = None,
        key_id: str | None = SIGNING_KEY_ID,
    ) -> str:
        """HMAC over the package checksum bound to the validity window.

        When a window is present it is part of the signed message, so tampering with the
        stored valid_from/not_after breaks the signature (the window is tamper-evident,
        not merely stored alongside). When both are None the legacy window-less message is
        used, so signatures produced before this window existed still verify.
        """
        secret = signing_secret_for_key_id(key_id)
        if valid_from is None and not_after is None:
            message = checksum_sha256
        else:
            message = f"{checksum_sha256}|{self._iso(valid_from)}|{self._iso(not_after)}"
        return hmac.new(secret, message.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _iso(value: datetime | None) -> str:
        # Canonical UTC representation so the signed window string is identical at signing
        # time (aware datetime) and at verify time (some backends round-trip it naive).
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    def _add_event(
        self,
        *,
        job: ExportJob,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        details_json: dict | None,
        created_by_user_id: uuid.UUID | None,
    ) -> ExportJobEvent:
        row = ExportJobEvent(
            organization_id=job.organization_id,
            export_job_id=job.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            details_json=details_json,
            created_by_user_id=created_by_user_id,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def add_event(
        self,
        *,
        job: ExportJob,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        details_json: dict | None,
        created_by_user_id: uuid.UUID | None,
    ) -> ExportJobEvent:
        return self._add_event(
            job=job,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            details_json=details_json,
            created_by_user_id=created_by_user_id,
        )

    def create_completed_binary_export_job(
        self,
        *,
        organization_id: uuid.UUID,
        source_report_id: uuid.UUID | None,
        export_type: str,
        title: str,
        description: str | None,
        file_path: str,
        file_format: str,
        file_size_bytes: int,
        checksum_sha256: str,
        requested_by_user_id: uuid.UUID,
        validity_days: int | None = None,
    ) -> ExportJob:
        job = self.create_job(
            organization_id=organization_id,
            export_type=export_type,
            title=title,
            description=description,
            source_report_id=source_report_id,
            framework_id=None,
            period_start=None,
            period_end=None,
            metadata_json={
                "file_path": file_path,
                "format": file_format,
                "file_size_bytes": file_size_bytes,
            },
            requested_by_user_id=requested_by_user_id,
        )

        job.status = "processing"
        job.started_at = self.now()
        self.db.flush()
        self._add_event(
            job=job,
            event_type="export.started",
            from_status="queued",
            to_status="processing",
            details_json={"source_report_id": str(source_report_id) if source_report_id else None},
            created_by_user_id=requested_by_user_id,
        )

        completed_at = self.now()
        valid_from, not_after = self.validity_window(validity_days)
        manifest = {
            "export_job_id": str(job.id),
            "source_report_id": str(source_report_id) if source_report_id else None,
            "file_path": file_path,
            "file_format": file_format,
            "file_size_bytes": file_size_bytes,
            "generated_at": completed_at.isoformat(),
            "valid_from": valid_from.isoformat(),
            "not_after": not_after.isoformat(),
            "package_checksum_sha256": checksum_sha256,
        }
        provenance = {
            "source_models": ["compliance_reports", "compliance_report_sections"],
            "generated_at": completed_at.isoformat(),
            "generated_by_user_id": str(requested_by_user_id),
        }
        package_json = {
            "package_version": job.package_version,
            "export_type": export_type,
            "organization_id": str(organization_id),
            "generated_at": completed_at.isoformat(),
            "title": title,
            "manifest": manifest,
            "provenance": provenance,
            "storage": {"file_path": file_path, "format": file_format},
        }

        job.package_json = package_json
        job.manifest_json = manifest
        job.provenance_json = provenance
        job.checksum_sha256 = checksum_sha256
        job.valid_from = valid_from
        job.not_after = not_after
        job.integrity_signature = self.compute_integrity_signature(
            checksum_sha256, valid_from=valid_from, not_after=not_after, key_id=SIGNING_KEY_ID
        )
        job.signing_key_id = SIGNING_KEY_ID
        job.signature_algorithm = INTEGRITY_ALGORITHM
        job.status = "completed"
        job.completed_at = completed_at
        self.db.flush()

        self._add_event(
            job=job,
            event_type="export.completed",
            from_status="processing",
            to_status="completed",
            details_json={"checksum_sha256": checksum_sha256, "file_path": file_path},
            created_by_user_id=requested_by_user_id,
        )
        return job

    def require_job(self, *, organization_id: uuid.UUID, export_job_id: uuid.UUID) -> ExportJob:
        row = self.repo.get_job(export_job_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
        return row

    def require_source_report(self, *, organization_id: uuid.UUID, source_report_id: uuid.UUID) -> ComplianceReport:
        report = self.db.execute(select(ComplianceReport).where(ComplianceReport.id == source_report_id)).scalar_one_or_none()
        if report is None or report.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_report_id does not belong to organization")
        return report

    def require_active_framework(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> Framework:
        framework = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
        org_framework = self.db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.framework_id == framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if org_framework is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="framework_id is not active for organization")
        return framework

    def create_job(
        self,
        *,
        organization_id: uuid.UUID,
        export_type: str,
        title: str | None,
        description: str | None,
        source_report_id: uuid.UUID | None,
        framework_id: uuid.UUID | None,
        period_start: datetime | None,
        period_end: datetime | None,
        metadata_json: dict | None,
        requested_by_user_id: uuid.UUID,
    ) -> ExportJob:
        self.validate_export_type(export_type)
        self.validate_period_window(period_start, period_end)
        if source_report_id is not None:
            self.require_source_report(organization_id=organization_id, source_report_id=source_report_id)
        if framework_id is not None:
            self.require_active_framework(organization_id=organization_id, framework_id=framework_id)

        job = ExportJob(
            organization_id=organization_id,
            export_type=export_type,
            title=title or f"{export_type.replace('_', ' ').title()} Export",
            description=description,
            status="queued",
            requested_by_user_id=requested_by_user_id,
            source_report_id=source_report_id,
            framework_id=framework_id,
            period_start=period_start,
            period_end=period_end,
            package_version=PACKAGE_VERSION,
            immutable_after_completion=True,
            metadata_json=metadata_json,
        )
        self.db.add(job)
        self.db.flush()
        self._add_event(
            job=job,
            event_type="export.created",
            from_status=None,
            to_status=job.status,
            details_json={"export_type": job.export_type},
            created_by_user_id=requested_by_user_id,
        )
        return job

    def _build_compliance_report_data(self, *, organization_id: uuid.UUID, source_report_id: uuid.UUID) -> tuple[dict, list[str], dict]:
        report = self.require_source_report(organization_id=organization_id, source_report_id=source_report_id)
        sections = ReportRepository(self.db).list_sections(organization_id, report.id)
        payload = {
            "report": {
                "id": str(report.id),
                "report_type": report.report_type,
                "title": report.title,
                "description": report.description,
                "status": report.status,
                "framework_id": str(report.framework_id) if report.framework_id else None,
                "generated_at": report.generated_at.isoformat(),
                "provenance_json": report.provenance_json or {},
                "inputs_summary_json": report.inputs_summary_json or {},
            },
            "sections": [
                {
                    "id": str(item.id),
                    "section_key": item.section_key,
                    "title": item.title,
                    "body_markdown": item.body_markdown,
                    "data_json": item.data_json or {},
                    "provenance_json": item.provenance_json or {},
                    "sort_order": item.sort_order,
                    "created_at": item.created_at.isoformat(),
                }
                for item in sections
            ],
            "caveat": REPORT_CAVEAT,
        }
        included_sections = [item.section_key for item in sections]
        source_counts = {"report_count": 1, "section_count": len(sections)}
        return payload, included_sections, source_counts

    def _build_framework_readiness_data(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> tuple[dict, list[str], dict]:
        readiness = ReportService(self.db).framework_readiness_data(organization_id, framework_id)
        framework = self.require_active_framework(organization_id=organization_id, framework_id=framework_id)
        data = {
            "framework": {
                "id": str(framework.id),
                "code": framework.code,
                "name": framework.name,
                "status": framework.status,
                "coverage_level": framework.coverage_level,
            },
            "readiness": {
                **readiness,
                "framework_id": str(readiness["framework_id"]),
            },
            "caveat": REPORT_CAVEAT,
        }
        return data, ["framework_scope", "readiness"], {"framework_count": 1, "snapshot_count": len(readiness["latest_score_snapshots"])}

    def _build_evidence_manifest_data(self, *, organization_id: uuid.UUID) -> tuple[dict, list[str], dict]:
        items = self.db.execute(
            select(EvidenceItem)
            .where(EvidenceItem.organization_id == organization_id)
            .order_by(EvidenceItem.created_at.asc(), EvidenceItem.id.asc())
        ).scalars().all()

        links = self.db.execute(
            select(EvidenceControlLink)
            .where(
                EvidenceControlLink.organization_id == organization_id,
                EvidenceControlLink.link_status == "active",
            )
            .order_by(EvidenceControlLink.created_at.asc(), EvidenceControlLink.id.asc())
        ).scalars().all()

        link_counts: dict[str, int] = {}
        for link in links:
            key = str(link.evidence_item_id)
            link_counts[key] = link_counts.get(key, 0) + 1

        data = {
            "evidence_items": [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "description": item.description,
                    "evidence_type": item.evidence_type,
                    "source": item.source,
                    "status": item.status,
                    "review_status": item.review_status,
                    "freshness_status": item.freshness_status,
                    "valid_from": item.valid_from.isoformat() if item.valid_from else None,
                    "valid_until": item.valid_until.isoformat() if item.valid_until else None,
                    "collected_at": item.collected_at.isoformat() if item.collected_at else None,
                    "external_reference_url": item.external_reference_url,
                    "linked_controls_count": link_counts.get(str(item.id), 0),
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in items
            ],
            "link_summary": {"active_evidence_control_links": len(links)},
            "caveat": REPORT_CAVEAT,
        }
        return data, ["evidence_manifest"], {"evidence_item_count": len(items), "active_link_count": len(links)}

    def _build_risk_register_data(self, *, organization_id: uuid.UUID) -> tuple[dict, list[str], dict]:
        risks = self.db.execute(
            select(Risk)
            .where(Risk.organization_id == organization_id)
            .order_by(Risk.created_at.asc(), Risk.id.asc())
        ).scalars().all()
        risk_summary = RiskService(self.db).summary(organization_id)

        active_control_links = self.db.execute(
            select(RiskControlLink)
            .where(RiskControlLink.organization_id == organization_id, RiskControlLink.status == "active")
            .order_by(RiskControlLink.created_at.asc(), RiskControlLink.id.asc())
        ).scalars().all()
        active_evidence_links = self.db.execute(
            select(RiskEvidenceLink)
            .where(RiskEvidenceLink.organization_id == organization_id, RiskEvidenceLink.status == "active")
            .order_by(RiskEvidenceLink.created_at.asc(), RiskEvidenceLink.id.asc())
        ).scalars().all()

        control_counts: dict[str, int] = {}
        for link in active_control_links:
            key = str(link.risk_id)
            control_counts[key] = control_counts.get(key, 0) + 1
        evidence_counts: dict[str, int] = {}
        for link in active_evidence_links:
            key = str(link.risk_id)
            evidence_counts[key] = evidence_counts.get(key, 0) + 1

        data = {
            "summary": risk_summary,
            "risks": [
                {
                    "id": str(risk.id),
                    "title": risk.title,
                    "category": risk.category,
                    "status": risk.status,
                    "severity": risk.severity,
                    "likelihood": risk.likelihood,
                    "impact": risk.impact,
                    "inherent_score": risk.inherent_score,
                    "residual_score": risk.residual_score,
                    "treatment_strategy": risk.treatment_strategy,
                    "owner_user_id": str(risk.owner_user_id) if risk.owner_user_id else None,
                    "linked_controls_count": control_counts.get(str(risk.id), 0),
                    "linked_evidence_count": evidence_counts.get(str(risk.id), 0),
                    "created_at": risk.created_at.isoformat(),
                    "updated_at": risk.updated_at.isoformat(),
                }
                for risk in risks
            ],
            "caveat": REPORT_CAVEAT,
        }
        return data, ["risk_summary", "risk_rows"], {"risk_count": len(risks)}

    def _build_task_execution_data(self, *, organization_id: uuid.UUID) -> tuple[dict, list[str], dict]:
        summary = TaskService(self.db).summary(organization_id)
        tasks = self.db.execute(
            select(Task)
            .where(Task.organization_id == organization_id)
            .order_by(Task.created_at.asc(), Task.id.asc())
        ).scalars().all()
        data = {
            "summary": summary,
            "tasks": [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority,
                    "task_type": task.task_type,
                    "owner_user_id": str(task.owner_user_id) if task.owner_user_id else None,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "linked_entity_type": task.linked_entity_type,
                    "linked_entity_id": str(task.linked_entity_id) if task.linked_entity_id else None,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                }
                for task in tasks
            ],
            "caveat": REPORT_CAVEAT,
        }
        return data, ["task_summary", "task_rows"], {"task_count": len(tasks)}

    def _build_executive_summary_data(self, *, organization_id: uuid.UUID, export_type: str) -> tuple[dict, list[str], dict]:
        report_type = "audit_preparation" if export_type == "audit_preparation_json" else "executive_summary"
        sections, inputs_summary, provenance = ReportService(self.db).build_report(
            organization_id=organization_id,
            report_type=report_type,
            framework_id=None,
        )
        latest_scores = self.db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.organization_id == organization_id)
            .order_by(ScoreSnapshot.calculated_at.desc())
            .limit(10)
        ).scalars().all()
        data = {
            "summary_inputs": inputs_summary,
            "sections": [
                {
                    "section_key": section["section_key"],
                    "title": section["title"],
                    "data_json": section["data_json"],
                    "provenance_json": section["provenance_json"],
                }
                for section in sections
            ],
            "latest_score_snapshots": [
                {
                    "id": str(item.id),
                    "snapshot_type": item.snapshot_type,
                    "score": item.score,
                    "grade": item.grade,
                    "calculated_at": item.calculated_at.isoformat(),
                }
                for item in latest_scores
            ],
            "caveat": REPORT_CAVEAT,
        }
        return data, [section["section_key"] for section in sections], provenance.get("source_model_counts", {})

    def _build_data_for_type(self, *, job: ExportJob) -> tuple[dict, list[str], dict]:
        if job.export_type == "compliance_report_json":
            if job.source_report_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_report_id is required for compliance_report_json")
            return self._build_compliance_report_data(organization_id=job.organization_id, source_report_id=job.source_report_id)
        if job.export_type == "framework_readiness_json":
            if job.framework_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="framework_id is required for framework_readiness_json")
            return self._build_framework_readiness_data(organization_id=job.organization_id, framework_id=job.framework_id)
        if job.export_type == "evidence_manifest_json":
            return self._build_evidence_manifest_data(organization_id=job.organization_id)
        if job.export_type == "risk_register_json":
            return self._build_risk_register_data(organization_id=job.organization_id)
        if job.export_type == "task_execution_json":
            return self._build_task_execution_data(organization_id=job.organization_id)
        if job.export_type in {"executive_summary_json", "audit_preparation_json"}:
            return self._build_executive_summary_data(organization_id=job.organization_id, export_type=job.export_type)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export_type")

    def run_job(self, *, job: ExportJob, actor_user_id: uuid.UUID) -> ExportJob:
        if job.status not in {"draft", "queued", "failed"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export job cannot be run from current status")

        previous_status = job.status
        now = self.now()
        job.status = "processing"
        job.started_at = now
        job.failed_at = None
        job.error_message = None
        self.db.flush()
        self._add_event(
            job=job,
            event_type="export.started",
            from_status=previous_status,
            to_status=job.status,
            details_json=None,
            created_by_user_id=actor_user_id,
        )

        try:
            data, included_sections, source_counts = self._build_data_for_type(job=job)
            generated_at = self.now()
            valid_from, not_after = self.validity_window((job.metadata_json or {}).get("validity_days"))
            manifest = {
                "export_job_id": str(job.id),
                "source_report_id": str(job.source_report_id) if job.source_report_id else None,
                "framework_id": str(job.framework_id) if job.framework_id else None,
                "period_start": job.period_start.isoformat() if job.period_start else None,
                "period_end": job.period_end.isoformat() if job.period_end else None,
                "included_sections": included_sections,
                "source_counts": source_counts,
                "generated_at": generated_at.isoformat(),
                "valid_from": valid_from.isoformat(),
                "not_after": not_after.isoformat(),
                "package_checksum_sha256": None,
                "integrity_signature_algorithm": INTEGRITY_ALGORITHM,
                "signing_key_id": SIGNING_KEY_ID,
            }
            provenance = {
                "source_models": sorted(list(source_counts.keys())),
                "source_counts": source_counts,
                "generated_at": generated_at.isoformat(),
                "generated_by_user_id": str(actor_user_id),
            }
            package_json = {
                "package_version": job.package_version,
                "export_type": job.export_type,
                "organization_id": str(job.organization_id),
                "generated_at": generated_at.isoformat(),
                "generated_by_user_id": str(actor_user_id),
                "title": job.title,
                "caveat": EXPORT_CAVEAT,
                "manifest": manifest,
                "data": data,
                "provenance": provenance,
            }

            checksum = self.compute_checksum(package_json)
            signature = self.compute_integrity_signature(
                checksum, valid_from=valid_from, not_after=not_after, key_id=SIGNING_KEY_ID
            )
            package_json["manifest"]["package_checksum_sha256"] = checksum

            job.package_json = package_json
            job.manifest_json = manifest | {"package_checksum_sha256": checksum}
            job.provenance_json = provenance
            job.checksum_sha256 = checksum
            job.valid_from = valid_from
            job.not_after = not_after
            job.integrity_signature = signature
            job.signing_key_id = SIGNING_KEY_ID
            job.signature_algorithm = INTEGRITY_ALGORITHM
            job.status = "completed"
            job.completed_at = generated_at
            job.failed_at = None
            job.error_message = None
            self.db.flush()

            self._add_event(
                job=job,
                event_type="export.completed",
                from_status="processing",
                to_status=job.status,
                details_json={"checksum_sha256": checksum},
                created_by_user_id=actor_user_id,
            )
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.failed_at = self.now()
            job.error_message = str(exc)
            self.db.flush()
            self._add_event(
                job=job,
                event_type="export.failed",
                from_status="processing",
                to_status=job.status,
                details_json={"error_message": str(exc)},
                created_by_user_id=actor_user_id,
            )
            raise

    def cancel_job(self, *, job: ExportJob, actor_user_id: uuid.UUID, reason: str | None) -> ExportJob:
        if job.status == "cancelled":
            return job
        if job.status not in {"draft", "queued", "failed"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export job cannot be cancelled from current status")
        before = job.status
        job.status = "cancelled"
        job.cancelled_at = self.now()
        self.db.flush()
        self._add_event(
            job=job,
            event_type="export.cancelled",
            from_status=before,
            to_status=job.status,
            details_json={"reason": reason},
            created_by_user_id=actor_user_id,
        )
        return job

    def archive_job(self, *, job: ExportJob, actor_user_id: uuid.UUID) -> ExportJob:
        if job.status == "archived":
            return job
        now = self.now()
        if job.legal_hold:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export job cannot be archived while legal hold is enabled")
        locked_until = self.as_utc(job.locked_until)
        if locked_until is not None and locked_until > now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export job is currently locked and cannot be archived")
        before = job.status
        job.status = "archived"
        job.archived_at = now
        self.db.flush()
        self._add_event(
            job=job,
            event_type="export.archived",
            from_status=before,
            to_status=job.status,
            details_json=None,
            created_by_user_id=actor_user_id,
        )
        return job

    def verify_job(self, *, job: ExportJob, actor_user_id: uuid.UUID) -> dict[str, Any]:
        if job.status != "completed" or job.package_json is None or job.checksum_sha256 is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export job is not completed")

        recomputed_checksum = self.compute_checksum(job.package_json)
        checksum_match = recomputed_checksum == job.checksum_sha256

        # Recompute the signature over the STORED validity window and under the RECORDED
        # signing_key_id, so tampering with the window breaks the signature and a future
        # key rotation stays verifiable without invalidating historical exports.
        signature_match: bool | None
        if job.signature_algorithm == INTEGRITY_ALGORITHM and job.integrity_signature is not None:
            recomputed_signature = self.compute_integrity_signature(
                recomputed_checksum,
                valid_from=job.valid_from,
                not_after=job.not_after,
                key_id=job.signing_key_id,
            )
            signature_match = recomputed_signature == job.integrity_signature
        else:
            signature_match = None

        checked_at = self.now()
        # Expiry: a signature past its not_after is no longer valid. Normalise the stored
        # value to UTC-aware first (some backends round-trip a naive datetime).
        not_after = job.not_after
        if not_after is not None and not_after.tzinfo is None:
            not_after = not_after.replace(tzinfo=UTC)
        expired = bool(not_after is not None and checked_at > not_after)
        # Revocation: an export whose attestation sign-off has been revoked (with no
        # active attestation remaining) fails verification -- the DB "revoked" flag now
        # actually affects trust, instead of the artifact validating cryptographically
        # forever regardless of it.
        revoked = job.attestation_status == "revoked"

        crypto_ok = checksum_match and (signature_match if signature_match is not None else True)
        valid = crypto_ok and not expired and not revoked

        if not checksum_match:
            reason = "checksum_mismatch"
        elif signature_match is False:
            reason = "invalid_signature"
        elif revoked:
            reason = "revoked"
        elif expired:
            reason = "expired"
        else:
            reason = "valid"

        self._add_event(
            job=job,
            event_type="export.verified",
            from_status=job.status,
            to_status=job.status,
            details_json={
                "valid": valid,
                "checksum_match": checksum_match,
                "signature_match": signature_match,
                "expired": expired,
                "revoked": revoked,
                "reason": reason,
                "checked_at": checked_at.isoformat(),
            },
            created_by_user_id=actor_user_id,
        )

        return {
            "valid": valid,
            "checksum_match": checksum_match,
            "signature_match": signature_match,
            "expired": expired,
            "revoked": revoked,
            "reason": reason,
            "not_after": job.not_after,
            "checked_at": checked_at,
        }

    def verification_history(self, *, organization_id: uuid.UUID, export_job_id: uuid.UUID) -> list[ExportJobEvent]:
        stmt = (
            select(ExportJobEvent)
            .where(
                ExportJobEvent.organization_id == organization_id,
                ExportJobEvent.export_job_id == export_job_id,
                ExportJobEvent.event_type == "export.verified",
            )
            .order_by(ExportJobEvent.created_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        now = self.now()
        since_30d = now - timedelta(days=30)
        since_24h = now - timedelta(hours=24)
        total_exports = int(
            self.db.execute(select(func.count(ExportJob.id)).where(ExportJob.organization_id == organization_id)).scalar_one()
        )
        queued_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.status == "queued",
                )
            ).scalar_one()
        )
        processing_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.status == "processing",
                )
            ).scalar_one()
        )
        completed_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.status == "completed",
                )
            ).scalar_one()
        )
        failed_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.status == "failed",
                )
            ).scalar_one()
        )
        archived_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.status == "archived",
                )
            ).scalar_one()
        )
        exports_last_30d = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.created_at >= since_30d,
                )
            ).scalar_one()
        )
        stale_queued_exports_24h = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.status == "queued",
                    ExportJob.created_at < since_24h,
                )
            ).scalar_one()
        )
        latest_completed_at = self.db.execute(
            select(func.max(ExportJob.completed_at)).where(
                ExportJob.organization_id == organization_id,
                ExportJob.completed_at.is_not(None),
            )
        ).scalar_one()
        latest_verified_at = self.db.execute(
            select(func.max(ExportJobEvent.created_at)).where(
                ExportJobEvent.organization_id == organization_id,
                ExportJobEvent.event_type == "export.verified",
            )
        ).scalar_one()

        verification_events = int(
            self.db.execute(
                select(func.count(ExportJobEvent.id)).where(
                    ExportJobEvent.organization_id == organization_id,
                    ExportJobEvent.event_type == "export.verified",
                )
            ).scalar_one()
        )
        verification_coverage_pct = round((verification_events / completed_exports) * 100, 2) if completed_exports else 0.0
        context_flags: list[str] = []
        if total_exports == 0:
            context_flags.append("no_exports_available")
        if stale_queued_exports_24h > 0:
            context_flags.append("stale_queued_exports_present")
        if processing_exports > 0:
            context_flags.append("exports_in_progress")
        if failed_exports > 0:
            context_flags.append("failed_exports_present")
        if completed_exports > 0 and verification_events == 0:
            context_flags.append("no_verified_exports")

        return {
            "total_exports": total_exports,
            "queued_exports": queued_exports,
            "processing_exports": processing_exports,
            "completed_exports": completed_exports,
            "failed_exports": failed_exports,
            "archived_exports": archived_exports,
            "exports_last_30d": exports_last_30d,
            "stale_queued_exports_24h": stale_queued_exports_24h,
            "verification_coverage_pct": verification_coverage_pct,
            "context_flags": context_flags,
            "latest_completed_at": latest_completed_at,
            "latest_verified_at": latest_verified_at,
        }
