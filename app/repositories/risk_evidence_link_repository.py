import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk_evidence_link import RiskEvidenceLink


class RiskEvidenceLinkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, organization_id: uuid.UUID, risk_id: uuid.UUID, evidence_item_id: uuid.UUID) -> RiskEvidenceLink | None:
        stmt = select(RiskEvidenceLink).where(
            RiskEvidenceLink.organization_id == organization_id,
            RiskEvidenceLink.risk_id == risk_id,
            RiskEvidenceLink.evidence_item_id == evidence_item_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_risk(self, organization_id: uuid.UUID, risk_id: uuid.UUID) -> list[RiskEvidenceLink]:
        stmt = select(RiskEvidenceLink).where(
            RiskEvidenceLink.organization_id == organization_id,
            RiskEvidenceLink.risk_id == risk_id,
            RiskEvidenceLink.status == "active",
        )
        return list(self.db.execute(stmt).scalars().all())
