import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.retention_policy import RetentionPolicy


class RetentionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_policy(self, policy_id: uuid.UUID) -> RetentionPolicy | None:
        return self.db.execute(select(RetentionPolicy).where(RetentionPolicy.id == policy_id)).scalar_one_or_none()

    def list_policies(self, organization_id: uuid.UUID) -> list[RetentionPolicy]:
        stmt = (
            select(RetentionPolicy)
            .where(RetentionPolicy.organization_id == organization_id)
            .order_by(RetentionPolicy.created_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def active_policy_for_entity(self, organization_id: uuid.UUID, entity_type: str) -> RetentionPolicy | None:
        stmt = (
            select(RetentionPolicy)
            .where(
                RetentionPolicy.organization_id == organization_id,
                RetentionPolicy.entity_type == entity_type,
                RetentionPolicy.status == "active",
            )
            .order_by(RetentionPolicy.updated_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
