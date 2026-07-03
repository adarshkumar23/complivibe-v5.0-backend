import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.nlp.signal_classifier import classify_signal_severity
from app.models.ai_risk_signal import AIRiskSignal
from app.models.ai_system import AISystem
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_SIGNAL_TYPES = {
    "new_training_data_source",
    "deployment_scope_expansion",
    "model_version_change",
    "output_distribution_shift",
    "new_use_case",
    "new_geographic_deployment",
    "high_volume_threshold_exceeded",
    "bias_signal",
}
ALLOWED_SIGNAL_STATUS = {"new", "reviewed", "actioned", "dismissed"}
REVIEW_ACTION_MAP = {
    "acknowledge": "reviewed",
    "action_taken": "actioned",
    "dismiss": "dismissed",
}


class SignalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def get_signal(self, org_id: uuid.UUID, signal_id: uuid.UUID) -> AIRiskSignal:
        row = self.db.execute(
            select(AIRiskSignal).where(
                AIRiskSignal.organization_id == org_id,
                AIRiskSignal.id == signal_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk signal not found")
        return row

    def emit_signal(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        signal_type: str,
        description: str,
        actor_id: uuid.UUID | None = None,
    ) -> AIRiskSignal | None:
        signal_type = validate_choice(signal_type, ALLOWED_SIGNAL_TYPES, "signal_type")
        self._require_system(org_id, system_id)
        cutoff = self.utcnow() - timedelta(days=7)
        existing = self.db.execute(
            select(AIRiskSignal).where(
                AIRiskSignal.organization_id == org_id,
                AIRiskSignal.ai_system_id == system_id,
                AIRiskSignal.signal_type == signal_type,
                AIRiskSignal.detected_at >= cutoff,
                AIRiskSignal.status != "dismissed",
            )
            .order_by(AIRiskSignal.detected_at.desc())
        ).scalars().first()
        if existing is not None:
            return existing

        now = self.utcnow()
        signal = AIRiskSignal(
            organization_id=org_id,
            ai_system_id=system_id,
            signal_type=signal_type,
            signal_description=description,
            detected_at=now,
            severity=classify_signal_severity(description),
            status="new",
            reviewed_by=None,
            reviewed_at=None,
            review_notes=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(signal)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "signal.emitted",
            actor_id=actor_id,
            actor_type="user" if actor_id else "system",
            ai_system_id=system_id,
            event_data={
                "signal_id": str(signal.id),
                "signal_type": signal.signal_type,
                "severity": signal.severity,
            },
        )
        AuditService(self.db).write_audit_log(
            action="signal.emitted",
            entity_type="ai_risk_signal",
            entity_id=signal.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "ai_system_id": str(system_id),
                "signal_type": signal.signal_type,
                "severity": signal.severity,
                "status": signal.status,
            },
            metadata_json={"source": "service"},
        )
        return signal

    def list_signals(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID | None = None,
        signal_type: str | None = None,
        status_value: str | None = None,
        severity: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AIRiskSignal]:
        stmt = select(AIRiskSignal).where(AIRiskSignal.organization_id == org_id)
        if system_id is not None:
            stmt = stmt.where(AIRiskSignal.ai_system_id == system_id)
        if signal_type is not None:
            signal_type = validate_choice(signal_type, ALLOWED_SIGNAL_TYPES, "signal_type")
            stmt = stmt.where(AIRiskSignal.signal_type == signal_type)
        if status_value is not None:
            status_value = validate_choice(status_value, ALLOWED_SIGNAL_STATUS, "status")
            stmt = stmt.where(AIRiskSignal.status == status_value)
        if severity is not None:
            if severity not in {"critical", "high", "medium", "low"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid severity filter")
            stmt = stmt.where(AIRiskSignal.severity == severity)

        safe_limit = max(1, min(int(limit), 200))
        return self.db.execute(
            stmt.order_by(AIRiskSignal.detected_at.desc()).offset(max(0, int(skip))).limit(safe_limit)
        ).scalars().all()

    def review_signal(
        self,
        org_id: uuid.UUID,
        signal_id: uuid.UUID,
        action: str,
        reviewer_id: uuid.UUID,
        notes: str | None = None,
    ) -> AIRiskSignal:
        row = self.get_signal(org_id, signal_id)
        status_value = REVIEW_ACTION_MAP.get(action)
        if status_value is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid review action")

        row.status = status_value
        row.reviewed_by = reviewer_id
        row.reviewed_at = self.utcnow()
        row.review_notes = notes
        row.updated_at = row.reviewed_at
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "signal.reviewed",
            actor_id=reviewer_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"signal_id": str(row.id), "status": row.status},
        )
        AuditService(self.db).write_audit_log(
            action="signal.reviewed",
            entity_type="ai_risk_signal",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=reviewer_id,
            after_json={
                "status": row.status,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            },
            metadata_json={"source": "api", "action": action},
        )
        return row
