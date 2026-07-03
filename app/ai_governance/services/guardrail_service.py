import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_guardrail_event import AIGuardrailEvent
from app.models.ai_policy_guardrail import AIPolicyGuardrail
from app.models.ai_system import AISystem
from app.platform.policy_engine.builtin_engine import get_policy_engine
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_GUARDRAIL_TYPES = {
    "data_scope",
    "user_scope",
    "action_scope",
    "geographic_scope",
    "financial_limit",
    "approval_required",
}
ALLOWED_VIOLATION_ACTIONS = {"alert_only", "block_and_alert", "require_approval"}
ALLOWED_EVENT_TYPES = {"check_passed", "violation_detected", "blocked"}


class GuardrailService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _validate_payload(self, payload: dict) -> None:
        if payload.get("guardrail_type") is not None and payload["guardrail_type"] not in ALLOWED_GUARDRAIL_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid guardrail_type")
        if payload.get("violation_action") is not None and payload["violation_action"] not in ALLOWED_VIOLATION_ACTIONS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid violation_action")

    def _require_system_if_set(self, org_id: uuid.UUID, system_id: uuid.UUID | None) -> None:
        if system_id is None:
            return
        exists = self.db.execute(
            select(AISystem.id).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")

    def _require_guardrail(self, org_id: uuid.UUID, guardrail_id: uuid.UUID) -> AIPolicyGuardrail:
        row = self.db.execute(
            select(AIPolicyGuardrail).where(
                AIPolicyGuardrail.organization_id == org_id,
                AIPolicyGuardrail.id == guardrail_id,
                AIPolicyGuardrail.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail not found")
        return row

    def create_guardrail(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> AIPolicyGuardrail:
        payload = data.model_dump()
        self._validate_payload(payload)
        self._require_system_if_set(org_id, payload.get("ai_system_id"))

        now = self.utcnow()
        row = AIPolicyGuardrail(
            organization_id=org_id,
            ai_system_id=payload.get("ai_system_id"),
            guardrail_type=payload["guardrail_type"],
            constraint_description=payload["constraint_description"],
            constraint_value=payload["constraint_value"],
            violation_action=payload.get("violation_action") or "alert_only",
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "guardrail.created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"guardrail_id": str(row.id), "guardrail_type": row.guardrail_type},
        )
        AuditService(self.db).write_audit_log(
            action="guardrail.created",
            entity_type="ai_policy_guardrail",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"guardrail_type": row.guardrail_type, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def get_guardrail(self, org_id: uuid.UUID, guardrail_id: uuid.UUID) -> AIPolicyGuardrail:
        return self._require_guardrail(org_id, guardrail_id)

    def list_guardrails(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        guardrail_type: str | None = None,
    ) -> list[AIPolicyGuardrail]:
        stmt = select(AIPolicyGuardrail).where(
            AIPolicyGuardrail.organization_id == org_id,
            AIPolicyGuardrail.deleted_at.is_(None),
        )
        if system_id is not None:
            stmt = stmt.where(AIPolicyGuardrail.ai_system_id == system_id)
        if is_active is not None:
            stmt = stmt.where(AIPolicyGuardrail.is_active.is_(is_active))
        if guardrail_type is not None:
            guardrail_type = validate_choice(guardrail_type, ALLOWED_GUARDRAIL_TYPES, "guardrail_type")
            stmt = stmt.where(AIPolicyGuardrail.guardrail_type == guardrail_type)
        return self.db.execute(stmt.order_by(AIPolicyGuardrail.created_at.desc())).scalars().all()

    def update_guardrail(self, org_id: uuid.UUID, guardrail_id: uuid.UUID, data) -> AIPolicyGuardrail:
        row = self._require_guardrail(org_id, guardrail_id)
        payload = data.model_dump(exclude_unset=True)
        self._validate_payload(payload)
        if "ai_system_id" in payload:
            self._require_system_if_set(org_id, payload["ai_system_id"])

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def deactivate_guardrail(self, org_id: uuid.UUID, guardrail_id: uuid.UUID, user_id: uuid.UUID) -> AIPolicyGuardrail:
        row = self._require_guardrail(org_id, guardrail_id)
        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "guardrail.deactivated",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"guardrail_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="guardrail.deactivated",
            entity_type="ai_policy_guardrail",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_guardrail(self, org_id: uuid.UUID, guardrail_id: uuid.UUID, user_id: uuid.UUID) -> AIPolicyGuardrail:
        row = self._require_guardrail(org_id, guardrail_id)
        if row.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Deactivate guardrail before delete")
        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "guardrail.deleted",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"guardrail_id": str(row.id)},
        )
        return row

    def check_action(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        action_context: dict,
        actor_id: uuid.UUID,
    ) -> dict:
        self._require_system_if_set(org_id, system_id)
        engine = get_policy_engine()

        guardrails = self.db.execute(
            select(AIPolicyGuardrail).where(
                AIPolicyGuardrail.organization_id == org_id,
                AIPolicyGuardrail.is_active.is_(True),
                AIPolicyGuardrail.deleted_at.is_(None),
                or_(
                    AIPolicyGuardrail.ai_system_id == system_id,
                    AIPolicyGuardrail.ai_system_id.is_(None),
                ),
            )
        ).scalars().all()

        violations: list[str] = []
        blocked = False
        now = self.utcnow()

        for guardrail in guardrails:
            result = engine.evaluate(guardrail, action_context)
            event_type = "check_passed"

            if result.get("decision") == "block":
                violations.extend([str(item) for item in result.get("violations", [])])
                if guardrail.violation_action in {"block_and_alert", "require_approval"}:
                    blocked = True
                    event_type = "blocked"
                else:
                    event_type = "violation_detected"

            event = AIGuardrailEvent(
                organization_id=org_id,
                guardrail_id=guardrail.id,
                ai_system_id=system_id,
                event_type=event_type,
                context_json=action_context,
                created_at=now,
            )
            self.db.add(event)

        self.db.flush()

        payload = {
            "decision": "block" if blocked else "permit",
            "violations": violations,
            "guardrails_checked": len(guardrails),
            "blocked": blocked,
        }

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "guardrail.check_performed",
            actor_id=actor_id,
            actor_type="user",
            ai_system_id=system_id,
            event_data={
                "guardrails_checked": len(guardrails),
                "blocked": blocked,
                "violations": len(violations),
            },
        )
        AuditService(self.db).write_audit_log(
            action="guardrail.check_performed",
            entity_type="ai_guardrail_events",
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json=payload,
            metadata_json={"source": "api", "action_context": action_context},
        )
        return payload

    def get_guardrail_events(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID | None = None,
        guardrail_id: uuid.UUID | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[AIGuardrailEvent]:
        stmt = select(AIGuardrailEvent).where(AIGuardrailEvent.organization_id == org_id)
        if system_id is not None:
            stmt = stmt.where(AIGuardrailEvent.ai_system_id == system_id)
        if guardrail_id is not None:
            stmt = stmt.where(AIGuardrailEvent.guardrail_id == guardrail_id)
        if event_type is not None:
            event_type = validate_choice(event_type, ALLOWED_EVENT_TYPES, "event_type")
            stmt = stmt.where(AIGuardrailEvent.event_type == event_type)

        safe_limit = max(1, min(int(limit), 200))
        return self.db.execute(stmt.order_by(AIGuardrailEvent.created_at.desc()).limit(safe_limit)).scalars().all()
