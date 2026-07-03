import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.control import Control


class ControlRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, control_id: uuid.UUID) -> Control | None:
        return self.db.execute(select(Control).where(Control.id == control_id)).scalar_one_or_none()

    def list_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        criticality: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        business_unit_id: uuid.UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Control]:
        stmt = select(Control).where(Control.organization_id == organization_id)
        if status:
            stmt = stmt.where(Control.status == status)
        if criticality:
            stmt = stmt.where(Control.criticality == criticality)
        if owner_user_id:
            stmt = stmt.where(Control.owner_user_id == owner_user_id)
        if business_unit_id:
            stmt = stmt.where(Control.business_unit_id == business_unit_id)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Control.title.ilike(like), Control.description.ilike(like), Control.control_code.ilike(like)))

        stmt = stmt.order_by(Control.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
