import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.compliance_report import ComplianceReport
from app.models.evidence_item import EvidenceItem
from app.models.export_attestation import ExportAttestation
from app.models.export_job import ExportJob
from app.models.export_job_event import ExportJobEvent
from app.models.retention_policy import RetentionPolicy
from app.models.score_snapshot import ScoreSnapshot
from app.repositories.retention_repository import RetentionRepository
from app.core.validation import validate_choice

ALLOWED_RETENTION_ENTITY_TYPES = {
    "export_job",
    "compliance_report",
    "evidence_item",
    "score_snapshot",
    "audit_log",
}

# Non-export_job entity types have no dedicated locked_until/retention_until/
# legal_hold columns of their own -- they are governed purely by the org's
# RetentionPolicy for that entity_type, applied against the row's created_at.
# This mapping is what makes evaluate()/enforcement generic across all 5
# ALLOWED_RETENTION_ENTITY_TYPES instead of only ever handling export_job.
_DERIVED_ENTITY_MODELS: dict[str, type] = {
    "compliance_report": ComplianceReport,
    "evidence_item": EvidenceItem,
    "score_snapshot": ScoreSnapshot,
    "audit_log": AuditLog,
}


class RetentionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = RetentionRepository(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def validate_entity_type(entity_type: str) -> None:
        entity_type = validate_choice(entity_type, ALLOWED_RETENTION_ENTITY_TYPES, "entity_type", status_code=status.HTTP_400_BAD_REQUEST)
    def require_policy(self, organization_id: uuid.UUID, policy_id: uuid.UUID) -> RetentionPolicy:
        policy = self.repo.get_policy(policy_id)
        if policy is None or policy.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention policy not found")
        return policy

    def apply_policy_to_export(
        self,
        *,
        job: ExportJob,
        actor_user_id: uuid.UUID,
        policy: RetentionPolicy | None,
        lock_days: int | None,
        retention_days: int | None,
    ) -> ExportJob:
        now = self.now()
        effective_lock_days = lock_days if lock_days is not None else (policy.lock_days if policy else 0)
        effective_retention_days = retention_days if retention_days is not None else (policy.retention_days if policy else 0)

        job.locked_until = now + timedelta(days=effective_lock_days) if effective_lock_days > 0 else None
        job.retention_until = now + timedelta(days=effective_retention_days) if effective_retention_days > 0 else now

        if policy and policy.legal_hold_default:
            job.legal_hold = True
            job.legal_hold_reason = "Applied from retention policy default"
            job.legal_hold_set_by_user_id = actor_user_id
            job.legal_hold_set_at = now

        self.db.flush()
        return job

    def set_legal_hold(self, *, job: ExportJob, actor_user_id: uuid.UUID, enabled: bool, reason: str | None) -> ExportJob:
        if enabled and (reason is None or not reason.strip()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required when enabling legal hold")
        now = self.now()
        job.legal_hold = enabled
        if enabled:
            job.legal_hold_reason = reason
            job.legal_hold_set_by_user_id = actor_user_id
            job.legal_hold_set_at = now
        else:
            job.legal_hold_reason = reason
            job.legal_hold_set_by_user_id = actor_user_id
            job.legal_hold_set_at = now
        self.db.flush()
        return job

    def _evaluate_derived_entity(
        self,
        *,
        organization_id: uuid.UUID,
        entity_type: str,
        now: datetime,
        retained: list[dict[str, Any]],
        locked: list[dict[str, Any]],
        under_legal_hold: list[dict[str, Any]],
        retention_elapsed: list[dict[str, Any]],
        eligible_for_archive: list[dict[str, Any]],
    ) -> None:
        """Enforce retention for entity types with no dedicated locked_until/
        retention_until/legal_hold columns, by deriving those values from the
        org's active RetentionPolicy for this entity_type applied to created_at.
        Mirrors the export_job evaluation semantics above.
        """
        model = _DERIVED_ENTITY_MODELS[entity_type]
        policy = self.repo.active_policy_for_entity(organization_id, entity_type)
        rows = self.db.execute(select(model).where(model.organization_id == organization_id)).scalars().all()
        for row in rows:
            created_at = self.as_utc(row.created_at)
            if policy is None or created_at is None:
                # No active policy (or no created_at) means retention cannot be
                # determined for this row -- treat as retained, not silently
                # skipped, so it is still visible in the evaluation output.
                item = {
                    "entity_type": entity_type,
                    "entity_id": str(row.id),
                    "locked_until": None,
                    "retention_until": None,
                    "legal_hold": False,
                }
                retained.append(item)
                continue

            locked_until = created_at + timedelta(days=policy.lock_days) if policy.lock_days > 0 else None
            retention_until = created_at + timedelta(days=policy.retention_days)
            legal_hold = bool(policy.legal_hold_default)

            item = {
                "entity_type": entity_type,
                "entity_id": str(row.id),
                "locked_until": locked_until.isoformat() if locked_until else None,
                "retention_until": retention_until.isoformat(),
                "legal_hold": legal_hold,
            }

            if legal_hold:
                under_legal_hold.append(item)

            is_locked = locked_until is not None and locked_until > now
            if is_locked:
                locked.append(item)

            if retention_until <= now:
                retention_elapsed.append(item)
                if not legal_hold and not is_locked:
                    eligible_for_archive.append(item)
            else:
                retained.append(item)

    def evaluate(self, *, organization_id: uuid.UUID, entity_type: str | None) -> dict[str, list[dict[str, Any]]]:
        now = self.now()
        retained: list[dict[str, Any]] = []
        locked: list[dict[str, Any]] = []
        under_legal_hold: list[dict[str, Any]] = []
        retention_elapsed: list[dict[str, Any]] = []
        eligible_for_archive: list[dict[str, Any]] = []

        if entity_type is None or entity_type == "export_job":
            rows = self.db.execute(select(ExportJob).where(ExportJob.organization_id == organization_id)).scalars().all()
            for row in rows:
                item = {
                    "export_job_id": str(row.id),
                    "status": row.status,
                    "locked_until": row.locked_until.isoformat() if row.locked_until else None,
                    "retention_until": row.retention_until.isoformat() if row.retention_until else None,
                    "legal_hold": row.legal_hold,
                }
                if row.legal_hold:
                    under_legal_hold.append(item)
                locked_until = self.as_utc(row.locked_until)
                retention_until = self.as_utc(row.retention_until)
                if locked_until and locked_until > now:
                    locked.append(item)
                if retention_until and retention_until <= now:
                    retention_elapsed.append(item)
                    if not row.legal_hold and not (locked_until and locked_until > now):
                        eligible_for_archive.append(item)
                else:
                    retained.append(item)

        for derived_entity_type in _DERIVED_ENTITY_MODELS:
            if entity_type is not None and entity_type != derived_entity_type:
                continue
            self._evaluate_derived_entity(
                organization_id=organization_id,
                entity_type=derived_entity_type,
                now=now,
                retained=retained,
                locked=locked,
                under_legal_hold=under_legal_hold,
                retention_elapsed=retention_elapsed,
                eligible_for_archive=eligible_for_archive,
            )

        return {
            "retained": retained,
            "locked": locked,
            "under_legal_hold": under_legal_hold,
            "retention_elapsed": retention_elapsed,
            "eligible_for_archive": eligible_for_archive,
        }

    def summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        now = self.now()
        since_30d = now - timedelta(days=30)
        active_policies = int(
            self.db.execute(
                select(func.count(RetentionPolicy.id)).where(
                    RetentionPolicy.organization_id == organization_id,
                    RetentionPolicy.status == "active",
                )
            ).scalar_one()
        )
        locked_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.locked_until.is_not(None),
                    ExportJob.locked_until > now,
                )
            ).scalar_one()
        )
        exports_under_legal_hold = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.legal_hold.is_(True),
                )
            ).scalar_one()
        )
        retention_elapsed_exports = int(
            self.db.execute(
                select(func.count(ExportJob.id)).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.retention_until.is_not(None),
                    ExportJob.retention_until <= now,
                )
            ).scalar_one()
        )
        active_attestations = int(
            self.db.execute(
                select(func.count(ExportAttestation.id)).where(
                    ExportAttestation.organization_id == organization_id,
                    ExportAttestation.status == "active",
                )
            ).scalar_one()
        )
        revoked_attestations = int(
            self.db.execute(
                select(func.count(ExportAttestation.id)).where(
                    ExportAttestation.organization_id == organization_id,
                    ExportAttestation.status == "revoked",
                )
            ).scalar_one()
        )
        verifications_last_30d = int(
            self.db.execute(
                select(func.count(ExportJobEvent.id)).where(
                    ExportJobEvent.organization_id == organization_id,
                    ExportJobEvent.event_type == "export.verified",
                    ExportJobEvent.created_at >= since_30d,
                )
            ).scalar_one()
        )
        return {
            "active_policies": active_policies,
            "locked_exports": locked_exports,
            "exports_under_legal_hold": exports_under_legal_hold,
            "retention_elapsed_exports": retention_elapsed_exports,
            "active_attestations": active_attestations,
            "revoked_attestations": revoked_attestations,
            "verifications_last_30d": verifications_last_30d,
        }
