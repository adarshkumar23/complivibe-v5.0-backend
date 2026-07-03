import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control import Control
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem


class EvidenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def calculate_freshness_status(cls, valid_until: datetime | None) -> str:
        if valid_until is None:
            return "unknown"

        now = cls.now()
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until < now:
            return "expired"
        if valid_until <= now + timedelta(days=30):
            return "expiring_soon"
        return "current"

    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

    def require_evidence_in_org(self, organization_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
        evidence = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == evidence_id,
                EvidenceItem.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return evidence

    def set_review_status_and_emit(
        self,
        organization_id: uuid.UUID,
        evidence_id: uuid.UUID,
        *,
        review_status: str,
        review_notes: str | None,
        reviewed_by_user_id: uuid.UUID,
        triggered_by: str = "user_action",
    ) -> tuple[EvidenceItem, str]:
        evidence = self.require_evidence_in_org(organization_id, evidence_id)
        previous_status = evidence.review_status
        evidence.review_status = review_status
        evidence.review_notes = review_notes
        evidence.reviewed_by_user_id = reviewed_by_user_id
        evidence.reviewed_at = self.now()
        self.db.flush()

        if previous_status != evidence.review_status:
            EventBus.get_instance().emit(
                EventType.EVIDENCE_STATUS_CHANGED,
                EventPayload(
                    org_id=organization_id,
                    entity_type="evidence",
                    entity_id=evidence.id,
                    event_type=EventType.EVIDENCE_STATUS_CHANGED,
                    previous_value=previous_status,
                    new_value=evidence.review_status,
                    triggered_by=triggered_by,
                    db=self.db,
                ),
            )

        return evidence, previous_status

    def readiness_summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        total_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                )
            ).scalar_one()
        )

        verified_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status == "verified",
                )
            ).scalar_one()
        )

        needs_review_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                )
            ).scalar_one()
        )

        rejected_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status == "rejected",
                )
            ).scalar_one()
        )

        expired_evidence_items = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
        )

        controls_total = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )

        controls_with_any_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                )
            ).scalar_one()
        )

        controls_with_verified_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.review_status == "verified",
                )
            ).scalar_one()
        )

        controls_with_expired_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status != "archived",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
        )

        return {
            "total_evidence_items": total_evidence_items,
            "verified_evidence_items": verified_evidence_items,
            "needs_review_evidence_items": needs_review_evidence_items,
            "rejected_evidence_items": rejected_evidence_items,
            "expired_evidence_items": expired_evidence_items,
            "controls_with_verified_evidence": controls_with_verified_evidence,
            "controls_without_evidence": max(0, controls_total - controls_with_any_evidence),
            "controls_with_expired_evidence": controls_with_expired_evidence,
        }
