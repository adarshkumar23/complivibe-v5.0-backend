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
TERMINAL_SIGNAL_STATUSES = {"actioned", "dismissed"}
SIGNAL_STALE_DAYS = 14


class SignalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _is_stale_signal(self, *, detected_at: datetime, status_value: str) -> bool:
        if status_value != "new":
            return False
        detected_utc = self._as_utc(detected_at)
        now_utc = self._as_utc(self.utcnow())
        if detected_utc is None or now_utc is None:
            return False
        return detected_utc <= (now_utc - timedelta(days=SIGNAL_STALE_DAYS))

    def _system_map(self, org_id: uuid.UUID, system_ids: list[uuid.UUID]) -> dict[uuid.UUID, AISystem]:
        if not system_ids:
            return {}
        rows = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id.in_(system_ids),
            )
        ).scalars().all()
        return {row.id: row for row in rows}

    def signal_payload(self, row: AIRiskSignal, system: AISystem | None) -> dict:
        detected_utc = self._as_utc(row.detected_at)
        now_utc = self._as_utc(self.utcnow())
        reviewed_utc = self._as_utc(row.reviewed_at)
        signal_age_days = 0
        if detected_utc is not None and now_utc is not None:
            signal_age_days = max(0, int((now_utc - detected_utc).total_seconds() // 86400))
        reviewed_latency_hours: int | None = None
        if reviewed_utc is not None and detected_utc is not None:
            reviewed_latency_hours = max(0, int((reviewed_utc - detected_utc).total_seconds() // 3600))

        stale_signal = self._is_stale_signal(detected_at=row.detected_at, status_value=row.status)
        system_changed_since_detection = bool(
            system is not None
            and detected_utc is not None
            and self._as_utc(system.updated_at) is not None
            and self._as_utc(system.updated_at) > detected_utc
        )
        is_open = row.status == "new"
        needs_attention = is_open and row.severity in {"critical", "high"}
        has_review_notes = bool(row.review_notes is not None and str(row.review_notes).strip())

        context_flags: list[str] = []
        if is_open:
            context_flags.append("needs_review")
        if needs_attention:
            context_flags.append("high_priority_signal")
        if stale_signal:
            context_flags.append("stale_signal")
        if system_changed_since_detection:
            context_flags.append("system_changed_since_detection")
        if has_review_notes:
            context_flags.append("review_notes_present")

        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "ai_system_id": row.ai_system_id,
            "signal_type": row.signal_type,
            "signal_description": row.signal_description,
            "detected_at": row.detected_at,
            "severity": row.severity,
            "status": row.status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "review_notes": row.review_notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "is_open": is_open,
            "needs_attention": needs_attention,
            "has_review_notes": has_review_notes,
            "signal_age_days": signal_age_days,
            "reviewed_latency_hours": reviewed_latency_hours,
            "stale_signal": stale_signal,
            "system_deployment_status": system.deployment_status if system is not None else None,
            "system_changed_since_detection": system_changed_since_detection,
            "context_flags": context_flags,
        }

    def signal_payloads(self, org_id: uuid.UUID, rows: list[AIRiskSignal]) -> list[dict]:
        systems = self._system_map(org_id, [row.ai_system_id for row in rows])
        return [self.signal_payload(row, systems.get(row.ai_system_id)) for row in rows]

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
            self._require_system(org_id, system_id)
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
        if row.status in TERMINAL_SIGNAL_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Signal is already in a terminal status")
        if action == "dismiss":
            if notes is None or not notes.strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dismiss requires review notes")
            notes = notes.strip()
        elif notes is not None:
            notes = notes.strip() or None

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
