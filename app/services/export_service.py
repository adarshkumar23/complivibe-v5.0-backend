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

    def compute_integrity_signature(self, checksum_sha256: str) -> str:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        return hmac.new(secret, checksum_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

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
        manifest = {
            "export_job_id": str(job.id),
            "source_report_id": str(source_report_id) if source_report_id else None,
            "file_path": file_path,
            "file_format": file_format,
            "file_size_bytes": file_size_bytes,
            "generated_at": completed_at.isoformat(),
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
        job.integrity_signature = self.compute_integrity_signature(checksum_sha256)
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
            manifest = {
                "export_job_id": str(job.id),
                "source_report_id": str(job.source_report_id) if job.source_report_id else None,
                "framework_id": str(job.framework_id) if job.framework_id else None,
                "period_start": job.period_start.isoformat() if job.period_start else None,
                "period_end": job.period_end.isoformat() if job.period_end else None,
                "included_sections": included_sections,
                "source_counts": source_counts,
                "generated_at": generated_at.isoformat(),
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
            signature = self.compute_integrity_signature(checksum)
            package_json["manifest"]["package_checksum_sha256"] = checksum

            job.package_json = package_json
            job.manifest_json = manifest | {"package_checksum_sha256": checksum}
            job.provenance_json = provenance
            job.checksum_sha256 = checksum
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

        signature_match: bool | None
        if job.signature_algorithm == INTEGRITY_ALGORITHM and job.integrity_signature is not None:
            recomputed_signature = self.compute_integrity_signature(recomputed_checksum)
            signature_match = recomputed_signature == job.integrity_signature
        else:
            signature_match = None

        valid = checksum_match and (signature_match if signature_match is not None else True)
        checked_at = self.now()

        self._add_event(
            job=job,
            event_type="export.verified",
            from_status=job.status,
            to_status=job.status,
            details_json={
                "valid": valid,
                "checksum_match": checksum_match,
                "signature_match": signature_match,
                "checked_at": checked_at.isoformat(),
            },
            created_by_user_id=actor_user_id,
        )

        return {
            "valid": valid,
            "checksum_match": checksum_match,
            "signature_match": signature_match,
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
        since_30d = self.now() - timedelta(days=30)
        total_exports = int(
            self.db.execute(select(func.count(ExportJob.id)).where(ExportJob.organization_id == organization_id)).scalar_one()
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
        return {
            "total_exports": total_exports,
            "completed_exports": completed_exports,
            "failed_exports": failed_exports,
            "archived_exports": archived_exports,
            "exports_last_30d": exports_last_30d,
            "latest_completed_at": latest_completed_at,
            "latest_verified_at": latest_verified_at,
        }
