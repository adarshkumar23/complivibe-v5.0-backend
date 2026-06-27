import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_system import AISystem
from app.models.model_card import ModelCard
from app.services.audit_service import AuditService


class ModelCardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def compute_content_hash(card: ModelCard) -> str:
        content = json.dumps(
            {
                "intended_purpose": card.intended_purpose,
                "known_limitations": card.known_limitations,
                "approved_use_cases": card.approved_use_cases,
                "prohibited_use_cases": card.prohibited_use_cases,
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

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

    def _require_card(self, org_id: uuid.UUID, card_id: uuid.UUID) -> ModelCard:
        row = self.db.execute(
            select(ModelCard).where(
                ModelCard.organization_id == org_id,
                ModelCard.id == card_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model card not found")
        return row

    def create_card(self, org_id: uuid.UUID, system_id: uuid.UUID, data, created_by: uuid.UUID) -> ModelCard:
        self._require_system(org_id, system_id)
        max_version = self.db.execute(
            select(func.max(ModelCard.version)).where(
                ModelCard.organization_id == org_id,
                ModelCard.ai_system_id == system_id,
            )
        ).scalar_one_or_none()
        next_version = int(max_version or 0) + 1

        now = self.utcnow()
        row = ModelCard(
            organization_id=org_id,
            ai_system_id=system_id,
            version=next_version,
            intended_purpose=data.intended_purpose,
            training_data_description=data.training_data_description,
            training_data_cutoff_date=data.training_data_cutoff_date,
            known_limitations=data.known_limitations,
            performance_metrics=data.performance_metrics,
            approved_use_cases=data.approved_use_cases,
            prohibited_use_cases=data.prohibited_use_cases,
            bias_evaluation_results=data.bias_evaluation_results,
            human_oversight_requirements=data.human_oversight_requirements,
            content_hash=None,
            contact_owner_id=data.contact_owner_id,
            status="draft",
            published_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        row.content_hash = self.compute_content_hash(row)
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "model_card.created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"card_id": str(row.id), "version": row.version},
        )
        AuditService(self.db).write_audit_log(
            action="model_card.created",
            entity_type="model_card",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": row.status, "version": row.version, "content_hash": row.content_hash},
            metadata_json={"source": "api"},
        )
        return row

    def get_active_card(self, org_id: uuid.UUID, system_id: uuid.UUID) -> ModelCard:
        self._require_system(org_id, system_id)
        published = self.db.execute(
            select(ModelCard).where(
                ModelCard.organization_id == org_id,
                ModelCard.ai_system_id == system_id,
                ModelCard.status == "published",
            )
        ).scalar_one_or_none()
        if published is not None:
            return published

        latest_draft = self.db.execute(
            select(ModelCard)
            .where(
                ModelCard.organization_id == org_id,
                ModelCard.ai_system_id == system_id,
                ModelCard.status == "draft",
            )
            .order_by(ModelCard.version.desc())
        ).scalars().first()
        if latest_draft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model card not found")
        return latest_draft

    def get_card(self, org_id: uuid.UUID, card_id: uuid.UUID) -> ModelCard:
        return self._require_card(org_id, card_id)

    def list_cards(self, org_id: uuid.UUID, system_id: uuid.UUID | None = None, status_filter: str | None = None) -> list[ModelCard]:
        stmt = select(ModelCard).where(ModelCard.organization_id == org_id)
        if system_id is not None:
            stmt = stmt.where(ModelCard.ai_system_id == system_id)
        if status_filter is not None:
            if status_filter not in {"draft", "published", "archived"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status filter")
            stmt = stmt.where(ModelCard.status == status_filter)
        return self.db.execute(stmt.order_by(ModelCard.ai_system_id.asc(), ModelCard.version.desc())).scalars().all()

    def update_card(self, org_id: uuid.UUID, card_id: uuid.UUID, data) -> ModelCard:
        row = self._require_card(org_id, card_id)
        if row.status == "published":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Published cards are immutable")

        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(row, key, value)
        row.content_hash = self.compute_content_hash(row)
        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def publish_card(self, org_id: uuid.UUID, card_id: uuid.UUID, user_id: uuid.UUID) -> ModelCard:
        row = self._require_card(org_id, card_id)

        existing_published = self.db.execute(
            select(ModelCard).where(
                ModelCard.organization_id == org_id,
                ModelCard.ai_system_id == row.ai_system_id,
                ModelCard.status == "published",
                ModelCard.id != row.id,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if existing_published is not None:
            existing_published.status = "archived"
            existing_published.updated_at = now
            self.db.flush()

            AIGovernanceEventService.log(
                self.db,
                org_id,
                "model_card.archived",
                actor_id=user_id,
                actor_type="user",
                ai_system_id=row.ai_system_id,
                event_data={"card_id": str(existing_published.id), "version": existing_published.version},
            )
            AuditService(self.db).write_audit_log(
                action="model_card.archived",
                entity_type="model_card",
                entity_id=existing_published.id,
                organization_id=org_id,
                actor_user_id=user_id,
                after_json={"status": existing_published.status},
                metadata_json={"source": "api"},
            )

        row.status = "published"
        row.published_at = now
        row.updated_at = now
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "model_card.published",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"card_id": str(row.id), "version": row.version},
        )
        AuditService(self.db).write_audit_log(
            action="model_card.published",
            entity_type="model_card",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "published_at": row.published_at.isoformat() if row.published_at else None},
            metadata_json={"source": "api"},
        )
        return row
