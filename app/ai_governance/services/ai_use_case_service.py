import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_system import AISystem
from app.models.ai_use_case import AIUseCase
from app.models.user import User
from app.services.audit_service import AuditService


class AIUseCaseService:
    ALLOWED_USE_CASE_TYPES = {
        "decision_making",
        "classification",
        "generation",
        "recommendation",
        "monitoring",
        "automation",
        "other",
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="AI system not found in organization")
        return row

    def _require_owner(self, owner_id: uuid.UUID) -> None:
        owner = self.db.execute(select(User.id).where(User.id == owner_id)).scalar_one_or_none()
        if owner is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Business owner not found")

    def _validate_type(self, use_case_type: str) -> None:
        if use_case_type not in self.ALLOWED_USE_CASE_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid use_case_type")

    def create_use_case(self, org_id: uuid.UUID, system_id: uuid.UUID, data, created_by: uuid.UUID) -> AIUseCase:
        system = self._require_system(org_id, system_id)
        self._validate_type(data.use_case_type)
        self._require_owner(data.business_owner_id)

        row = AIUseCase(
            organization_id=org_id,
            ai_system_id=system.id,
            name=data.name,
            description=data.description,
            business_owner_id=data.business_owner_id,
            use_case_type=data.use_case_type,
            is_high_stakes=data.is_high_stakes,
            affected_groups=data.affected_groups,
            deployment_context=data.deployment_context,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "use_case.created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system.id,
            event_data={"use_case_id": str(row.id), "use_case_type": row.use_case_type},
        )
        if row.is_high_stakes:
            AIGovernanceEventService.log(
                self.db,
                org_id,
                "use_case.high_stakes_created",
                actor_id=created_by,
                actor_type="user",
                ai_system_id=system.id,
                event_data={"use_case_id": str(row.id), "name": row.name},
            )

        AuditService(self.db).write_audit_log(
            action="use_case.created",
            entity_type="ai_use_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "ai_system_id": str(system.id),
                "name": row.name,
                "use_case_type": row.use_case_type,
                "is_high_stakes": row.is_high_stakes,
            },
            metadata_json={"source": "api"},
        )
        if row.is_high_stakes:
            AuditService(self.db).write_audit_log(
                action="use_case.high_stakes_created",
                entity_type="ai_use_case",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=created_by,
                after_json={"is_high_stakes": True},
                metadata_json={"source": "api"},
            )
        return row

    def get_use_case(self, org_id: uuid.UUID, use_case_id: uuid.UUID) -> AIUseCase:
        row = self.db.execute(
            select(AIUseCase).where(
                AIUseCase.id == use_case_id,
                AIUseCase.organization_id == org_id,
                AIUseCase.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI use case not found")
        return row

    def list_use_cases(
        self,
        org_id: uuid.UUID,
        *,
        system_id: uuid.UUID | None = None,
        use_case_type: str | None = None,
        is_high_stakes: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AIUseCase]:
        stmt = select(AIUseCase).where(
            AIUseCase.organization_id == org_id,
            AIUseCase.deleted_at.is_(None),
        )
        if system_id is not None:
            stmt = stmt.where(AIUseCase.ai_system_id == system_id)
        if use_case_type is not None:
            stmt = stmt.where(AIUseCase.use_case_type == use_case_type)
        if is_high_stakes is not None:
            stmt = stmt.where(AIUseCase.is_high_stakes.is_(is_high_stakes))

        return (
            self.db.execute(stmt.order_by(AIUseCase.created_at.desc()).offset(skip).limit(limit))
            .scalars()
            .all()
        )

    def update_use_case(self, org_id: uuid.UUID, use_case_id: uuid.UUID, data, actor_id: uuid.UUID) -> AIUseCase:
        row = self.get_use_case(org_id, use_case_id)
        payload = data.model_dump(exclude_unset=True)
        if "use_case_type" in payload:
            self._validate_type(payload["use_case_type"])
        if payload.get("business_owner_id") is not None:
            self._require_owner(payload["business_owner_id"])

        before = {
            "name": row.name,
            "use_case_type": row.use_case_type,
            "is_high_stakes": row.is_high_stakes,
        }
        for key, value in payload.items():
            setattr(row, key, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="use_case.updated",
            entity_type="ai_use_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "name": row.name,
                "use_case_type": row.use_case_type,
                "is_high_stakes": row.is_high_stakes,
            },
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_use_case(self, org_id: uuid.UUID, use_case_id: uuid.UUID, user_id: uuid.UUID) -> AIUseCase:
        row = self.get_use_case(org_id, use_case_id)
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="use_case.deleted",
            entity_type="ai_use_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row
