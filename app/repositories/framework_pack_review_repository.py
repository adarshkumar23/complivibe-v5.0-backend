import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_pack_promotion_request import FrameworkPackPromotionRequest
from app.models.framework_pack_review_run import FrameworkPackReviewRun
from app.models.framework_pack_review_signoff import FrameworkPackReviewSignoff
from app.models.framework_review_escalation_event import FrameworkReviewEscalationEvent
from app.models.framework_review_sla_policy import FrameworkReviewSLAPolicy


class FrameworkPackReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_review(self, review_id: uuid.UUID) -> FrameworkPackReviewRun | None:
        return self.db.execute(
            select(FrameworkPackReviewRun).where(FrameworkPackReviewRun.id == review_id)
        ).scalar_one_or_none()

    def list_reviews(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> list[FrameworkPackReviewRun]:
        return self.db.execute(
            select(FrameworkPackReviewRun)
            .where(
                FrameworkPackReviewRun.organization_id == organization_id,
                FrameworkPackReviewRun.framework_id == framework_id,
            )
            .order_by(FrameworkPackReviewRun.started_at.desc())
        ).scalars().all()

    def list_signoffs(self, *, organization_id: uuid.UUID, review_run_id: uuid.UUID) -> list[FrameworkPackReviewSignoff]:
        return self.db.execute(
            select(FrameworkPackReviewSignoff)
            .where(
                FrameworkPackReviewSignoff.organization_id == organization_id,
                FrameworkPackReviewSignoff.review_run_id == review_run_id,
            )
            .order_by(FrameworkPackReviewSignoff.signed_at.asc())
        ).scalars().all()

    def get_signoff_by_signer(
        self,
        *,
        organization_id: uuid.UUID,
        review_run_id: uuid.UUID,
        signer_user_id: uuid.UUID,
    ) -> FrameworkPackReviewSignoff | None:
        return self.db.execute(
            select(FrameworkPackReviewSignoff).where(
                FrameworkPackReviewSignoff.organization_id == organization_id,
                FrameworkPackReviewSignoff.review_run_id == review_run_id,
                FrameworkPackReviewSignoff.signer_user_id == signer_user_id,
            )
        ).scalar_one_or_none()

    def get_promotion(self, promotion_id: uuid.UUID) -> FrameworkPackPromotionRequest | None:
        return self.db.execute(
            select(FrameworkPackPromotionRequest).where(FrameworkPackPromotionRequest.id == promotion_id)
        ).scalar_one_or_none()

    def list_promotions(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> list[FrameworkPackPromotionRequest]:
        return self.db.execute(
            select(FrameworkPackPromotionRequest)
            .where(
                FrameworkPackPromotionRequest.organization_id == organization_id,
                FrameworkPackPromotionRequest.framework_id == framework_id,
            )
            .order_by(FrameworkPackPromotionRequest.requested_at.desc())
        ).scalars().all()

    def get_assignment(self, assignment_id: uuid.UUID) -> FrameworkPackReviewAssignment | None:
        return self.db.execute(
            select(FrameworkPackReviewAssignment).where(FrameworkPackReviewAssignment.id == assignment_id)
        ).scalar_one_or_none()

    def list_assignments_for_review(
        self,
        *,
        organization_id: uuid.UUID,
        review_run_id: uuid.UUID,
    ) -> list[FrameworkPackReviewAssignment]:
        return self.db.execute(
            select(FrameworkPackReviewAssignment)
            .where(
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.review_run_id == review_run_id,
            )
            .order_by(FrameworkPackReviewAssignment.created_at.desc())
        ).scalars().all()

    def list_assignments_for_org(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> list[FrameworkPackReviewAssignment]:
        return self.db.execute(
            select(FrameworkPackReviewAssignment)
            .where(FrameworkPackReviewAssignment.organization_id == organization_id)
            .order_by(FrameworkPackReviewAssignment.created_at.desc())
        ).scalars().all()

    def list_assignments_for_user(
        self,
        *,
        organization_id: uuid.UUID,
        assigned_to_user_id: uuid.UUID,
    ) -> list[FrameworkPackReviewAssignment]:
        return self.db.execute(
            select(FrameworkPackReviewAssignment)
            .where(
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.assigned_to_user_id == assigned_to_user_id,
            )
            .order_by(FrameworkPackReviewAssignment.created_at.desc())
        ).scalars().all()

    def get_sla_policy(self, policy_id: uuid.UUID) -> FrameworkReviewSLAPolicy | None:
        return self.db.execute(
            select(FrameworkReviewSLAPolicy).where(FrameworkReviewSLAPolicy.id == policy_id)
        ).scalar_one_or_none()

    def list_sla_policies(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewSLAPolicy]:
        return self.db.execute(
            select(FrameworkReviewSLAPolicy)
            .where(FrameworkReviewSLAPolicy.organization_id == organization_id)
            .order_by(FrameworkReviewSLAPolicy.created_at.desc())
        ).scalars().all()

    def get_escalation_event(self, event_id: uuid.UUID) -> FrameworkReviewEscalationEvent | None:
        return self.db.execute(
            select(FrameworkReviewEscalationEvent).where(FrameworkReviewEscalationEvent.id == event_id)
        ).scalar_one_or_none()

    def list_escalation_events(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewEscalationEvent]:
        return self.db.execute(
            select(FrameworkReviewEscalationEvent)
            .where(FrameworkReviewEscalationEvent.organization_id == organization_id)
            .order_by(FrameworkReviewEscalationEvent.triggered_at.desc())
        ).scalars().all()
