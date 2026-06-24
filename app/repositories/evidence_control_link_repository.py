import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_control_link import EvidenceControlLink


class EvidenceControlLinkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, organization_id: uuid.UUID, evidence_item_id: uuid.UUID, control_id: uuid.UUID) -> EvidenceControlLink | None:
        stmt = select(EvidenceControlLink).where(
            EvidenceControlLink.organization_id == organization_id,
            EvidenceControlLink.evidence_item_id == evidence_item_id,
            EvidenceControlLink.control_id == control_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_evidence(self, organization_id: uuid.UUID, evidence_item_id: uuid.UUID) -> list[EvidenceControlLink]:
        stmt = select(EvidenceControlLink).where(
            EvidenceControlLink.organization_id == organization_id,
            EvidenceControlLink.evidence_item_id == evidence_item_id,
            EvidenceControlLink.link_status == "active",
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_for_control(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> list[EvidenceControlLink]:
        stmt = select(EvidenceControlLink).where(
            EvidenceControlLink.organization_id == organization_id,
            EvidenceControlLink.control_id == control_id,
            EvidenceControlLink.link_status == "active",
        )
        return list(self.db.execute(stmt).scalars().all())
