import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk_control_link import RiskControlLink


class RiskControlLinkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, organization_id: uuid.UUID, risk_id: uuid.UUID, control_id: uuid.UUID) -> RiskControlLink | None:
        stmt = select(RiskControlLink).where(
            RiskControlLink.organization_id == organization_id,
            RiskControlLink.risk_id == risk_id,
            RiskControlLink.control_id == control_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_risk(self, organization_id: uuid.UUID, risk_id: uuid.UUID) -> list[RiskControlLink]:
        stmt = select(RiskControlLink).where(
            RiskControlLink.organization_id == organization_id,
            RiskControlLink.risk_id == risk_id,
            RiskControlLink.status == "active",
        )
        return list(self.db.execute(stmt).scalars().all())
