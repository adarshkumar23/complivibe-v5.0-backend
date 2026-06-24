import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control_obligation_mapping import ControlObligationMapping


class ControlMappingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, organization_id: uuid.UUID, control_id: uuid.UUID, obligation_id: uuid.UUID) -> ControlObligationMapping | None:
        stmt = select(ControlObligationMapping).where(
            ControlObligationMapping.organization_id == organization_id,
            ControlObligationMapping.control_id == control_id,
            ControlObligationMapping.obligation_id == obligation_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_control(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> list[ControlObligationMapping]:
        stmt = select(ControlObligationMapping).where(
            ControlObligationMapping.organization_id == organization_id,
            ControlObligationMapping.control_id == control_id,
            ControlObligationMapping.status == "active",
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_for_obligation(self, organization_id: uuid.UUID, obligation_id: uuid.UUID) -> list[ControlObligationMapping]:
        stmt = select(ControlObligationMapping).where(
            ControlObligationMapping.organization_id == organization_id,
            ControlObligationMapping.obligation_id == obligation_id,
            ControlObligationMapping.status == "active",
        )
        return list(self.db.execute(stmt).scalars().all())
