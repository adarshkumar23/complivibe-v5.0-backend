import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.risk import Risk


class RiskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, risk_id: uuid.UUID) -> Risk | None:
        return self.db.execute(select(Risk).where(Risk.id == risk_id)).scalar_one_or_none()

    def list_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        business_unit_id: uuid.UUID | None = None,
        treatment_strategy: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Risk]:
        stmt = select(Risk).where(Risk.organization_id == organization_id)
        if status:
            stmt = stmt.where(Risk.status == status)
        if category:
            stmt = stmt.where(Risk.category == category)
        if severity:
            stmt = stmt.where(Risk.severity == severity)
        if owner_user_id:
            stmt = stmt.where(Risk.owner_user_id == owner_user_id)
        if business_unit_id:
            stmt = stmt.where(Risk.business_unit_id == business_unit_id)
        if treatment_strategy:
            stmt = stmt.where(Risk.treatment_strategy == treatment_strategy)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Risk.title.ilike(like), Risk.description.ilike(like)))

        stmt = stmt.order_by(Risk.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
