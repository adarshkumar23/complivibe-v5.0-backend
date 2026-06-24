import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.evidence_item import EvidenceItem


class EvidenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, evidence_id: uuid.UUID) -> EvidenceItem | None:
        return self.db.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id)).scalar_one_or_none()

    def list_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        review_status: str | None = None,
        freshness_status: str | None = None,
        evidence_type: str | None = None,
        source: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvidenceItem]:
        stmt = select(EvidenceItem).where(EvidenceItem.organization_id == organization_id)

        if review_status:
            stmt = stmt.where(EvidenceItem.review_status == review_status)
        if freshness_status:
            stmt = stmt.where(EvidenceItem.freshness_status == freshness_status)
        if evidence_type:
            stmt = stmt.where(EvidenceItem.evidence_type == evidence_type)
        if source:
            stmt = stmt.where(EvidenceItem.source == source)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(EvidenceItem.title.ilike(like), EvidenceItem.description.ilike(like)))

        stmt = stmt.order_by(EvidenceItem.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
