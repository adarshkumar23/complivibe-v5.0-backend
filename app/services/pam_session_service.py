import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_observability.services.lineage_service import LineageService
from app.models.pam_session_record import PAMSessionRecord
from app.schemas.pam_session import PAMSessionIngestRequest, PAMSessionUpdateRequest
from app.services.audit_service import AuditService

APPROVAL_STATUSES = {"approved", "missing", "denied", "unknown"}
RISK_STATUSES = {"monitor", "open", "accepted", "resolved"}


class PAMSessionService:
    """
    Passive PAM receiver. The API-key ingest path uses the shared inbound
    X-CompliVibe-Key pattern resolved by LineageService; this service never
    calls out to CyberArk, BeyondTrust, Teleport, or other PAM tools.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _comparable_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        return LineageService(self.db).resolve_org_by_api_key(raw_key)

    @staticmethod
    def _validate_status(value: str, allowed: set[str], field: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in allowed:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid {field}")
        return normalized

    @staticmethod
    def _approval_status(payload: PAMSessionIngestRequest) -> str:
        if payload.approval_status is not None:
            return PAMSessionService._validate_status(payload.approval_status, APPROVAL_STATUSES, "approval_status")
        if payload.approved_by or payload.approval_reference:
            return "approved"
        return "missing"

    @staticmethod
    def _risk_status_and_reason(
        *,
        approval_status: str,
        provided_risk_status: str | None = None,
        provided_reason: str | None = None,
    ) -> tuple[str, str | None]:
        if approval_status in {"missing", "denied"}:
            return "open", provided_reason or "Privileged session has no approval evidence"
        if provided_risk_status is not None:
            return PAMSessionService._validate_status(provided_risk_status, RISK_STATUSES, "risk_status"), provided_reason
        return "monitor", provided_reason

    @staticmethod
    def _snapshot(row: PAMSessionRecord) -> dict[str, Any]:
        return {
            "external_session_id": row.external_session_id,
            "pam_provider": row.pam_provider,
            "identity": row.identity,
            "privileged_account": row.privileged_account,
            "target_system": row.target_system,
            "target_resource_type": row.target_resource_type,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "approved_by": row.approved_by,
            "approval_reference": row.approval_reference,
            "session_recording_url": row.session_recording_url,
            "approval_status": row.approval_status,
            "risk_status": row.risk_status,
            "risk_reason": row.risk_reason,
            "flagged_by": str(row.flagged_by) if row.flagged_by else None,
            "flagged_at": row.flagged_at.isoformat() if row.flagged_at else None,
        }

    def _require_session(self, org_id: uuid.UUID, session_id: uuid.UUID) -> PAMSessionRecord:
        row = self.db.execute(
            select(PAMSessionRecord).where(
                PAMSessionRecord.organization_id == org_id,
                PAMSessionRecord.id == session_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAM session not found")
        return row

    def ingest_session(self, org_id: uuid.UUID, payload: PAMSessionIngestRequest) -> tuple[PAMSessionRecord, bool]:
        if payload.ended_at is not None and self._comparable_datetime(payload.ended_at) < self._comparable_datetime(payload.started_at):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ended_at cannot be before started_at")

        approval_status = self._approval_status(payload)
        risk_status, risk_reason = self._risk_status_and_reason(
            approval_status=approval_status,
            provided_risk_status=payload.risk_status,
        )
        now = self.utcnow()

        existing = self.db.execute(
            select(PAMSessionRecord).where(
                PAMSessionRecord.organization_id == org_id,
                PAMSessionRecord.external_session_id == payload.external_session_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            row = PAMSessionRecord(
                organization_id=org_id,
                external_session_id=payload.external_session_id,
                pam_provider=payload.pam_provider,
                identity=payload.identity,
                privileged_account=payload.privileged_account,
                target_system=payload.target_system,
                target_resource_type=payload.target_resource_type,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                approved_by=payload.approved_by,
                approval_reference=payload.approval_reference,
                session_recording_url=payload.session_recording_url,
                approval_status=approval_status,
                risk_status=risk_status,
                risk_reason=risk_reason,
                source="api_key_ingest",
                raw_payload=payload.raw_payload,
                ingested_at=now,
            )
            self.db.add(row)
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="pam_session.ingested",
                entity_type="pam_session_record",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=None,
                after_json=self._snapshot(row),
                metadata_json={"source": "api_key_ingest", "created": True},
            )
            return row, True

        before = self._snapshot(existing)
        existing.pam_provider = payload.pam_provider
        existing.identity = payload.identity
        existing.privileged_account = payload.privileged_account
        existing.target_system = payload.target_system
        existing.target_resource_type = payload.target_resource_type
        existing.started_at = payload.started_at
        existing.ended_at = payload.ended_at
        existing.approved_by = payload.approved_by
        existing.approval_reference = payload.approval_reference
        existing.session_recording_url = payload.session_recording_url
        existing.approval_status = approval_status
        existing.risk_status = risk_status
        existing.risk_reason = risk_reason
        existing.raw_payload = payload.raw_payload
        existing.ingested_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pam_session.ingest_updated",
            entity_type="pam_session_record",
            entity_id=existing.id,
            organization_id=org_id,
            actor_user_id=None,
            before_json=before,
            after_json=self._snapshot(existing),
            metadata_json={"source": "api_key_ingest", "created": False},
        )
        return existing, False

    def list_sessions(
        self,
        org_id: uuid.UUID,
        *,
        approval_status: str | None = None,
        risk_status: str | None = None,
        identity: str | None = None,
        target_system: str | None = None,
        limit: int = 100,
    ) -> list[PAMSessionRecord]:
        stmt = select(PAMSessionRecord).where(PAMSessionRecord.organization_id == org_id)
        if approval_status is not None:
            stmt = stmt.where(PAMSessionRecord.approval_status == self._validate_status(approval_status, APPROVAL_STATUSES, "approval_status"))
        if risk_status is not None:
            stmt = stmt.where(PAMSessionRecord.risk_status == self._validate_status(risk_status, RISK_STATUSES, "risk_status"))
        if identity is not None:
            stmt = stmt.where(PAMSessionRecord.identity == identity)
        if target_system is not None:
            stmt = stmt.where(PAMSessionRecord.target_system == target_system)
        return self.db.execute(stmt.order_by(PAMSessionRecord.started_at.desc()).limit(max(1, min(limit, 500)))).scalars().all()

    # Statuses that represent an *unapproved* privileged session signal for
    # governance purposes. BUG: this view used to filter on approval_status ==
    # "missing" only, which silently excluded "denied" sessions -- a session
    # whose approval was actively denied is at least as strong a governance
    # signal as one that simply lacks approval evidence, not something to hide
    # from this view.
    UNAPPROVED_RISK_APPROVAL_STATUSES = ("missing", "denied")

    def list_unapproved_risks(self, org_id: uuid.UUID, *, limit: int = 100) -> dict[str, Any]:
        stmt = (
            select(PAMSessionRecord)
            .where(
                PAMSessionRecord.organization_id == org_id,
                PAMSessionRecord.approval_status.in_(self.UNAPPROVED_RISK_APPROVAL_STATUSES),
            )
            .order_by(PAMSessionRecord.started_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        rows = self.db.execute(stmt).scalars().all()
        return {
            "total_unapproved_sessions": len(rows),
            "open_risk_sessions": sum(1 for row in rows if row.risk_status == "open"),
            "sessions": rows,
        }

    def flag_unapproved_session(self, org_id: uuid.UUID, session_id: uuid.UUID, actor_user_id: uuid.UUID) -> PAMSessionRecord:
        row = self._require_session(org_id, session_id)
        if row.approval_status == "approved" or row.approved_by or row.approval_reference:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approved PAM sessions cannot be flagged as unapproved")

        before = self._snapshot(row)
        # BUG: this used to unconditionally set approval_status = "missing", which
        # overwrote (and destroyed) an existing "denied" status with the weaker/less
        # specific "missing" value. A denied session's signal must be preserved, not
        # downgraded, when it gets flagged -- only sessions that don't already carry
        # a "denied" status get normalized to "missing" here.
        if row.approval_status != "denied":
            row.approval_status = "missing"
        row.risk_status = "open"
        row.risk_reason = "Privileged session has no approval evidence"
        row.flagged_by = actor_user_id
        row.flagged_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pam_session.unapproved_flagged",
            entity_type="pam_session_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._snapshot(row),
            metadata_json={"source": "api", "risk_signal": "missing_pam_approval"},
        )
        return row

    def update_session(
        self,
        org_id: uuid.UUID,
        session_id: uuid.UUID,
        payload: PAMSessionUpdateRequest,
        actor_user_id: uuid.UUID,
    ) -> PAMSessionRecord:
        row = self._require_session(org_id, session_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return row
        if updates.get("ended_at") is not None and self._comparable_datetime(updates["ended_at"]) < self._comparable_datetime(row.started_at):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ended_at cannot be before started_at")

        before = self._snapshot(row)
        for field, value in updates.items():
            if field == "approval_status" and value is not None:
                value = self._validate_status(value, APPROVAL_STATUSES, "approval_status")
            if field == "risk_status" and value is not None:
                value = self._validate_status(value, RISK_STATUSES, "risk_status")
            setattr(row, field, value)

        if row.approval_status in {"missing", "denied"} and row.risk_status != "accepted":
            row.risk_status = "open"
            row.risk_reason = row.risk_reason or "Privileged session has no approval evidence"
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pam_session.updated",
            entity_type="pam_session_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._snapshot(row),
            metadata_json={"source": "api"},
        )
        return row
