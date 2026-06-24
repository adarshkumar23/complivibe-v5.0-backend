import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.framework_review_assignment_suggestion import FrameworkReviewAssignmentSuggestion
from app.models.framework_reviewer_capacity_policy import FrameworkReviewerCapacityPolicy
from app.models.framework_reviewer_workload_snapshot import FrameworkReviewerWorkloadSnapshot


class FrameworkReviewCapacityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_capacity_policy(self, policy_id: uuid.UUID) -> FrameworkReviewerCapacityPolicy | None:
        return self.db.execute(
            select(FrameworkReviewerCapacityPolicy).where(FrameworkReviewerCapacityPolicy.id == policy_id)
        ).scalar_one_or_none()

    def list_capacity_policies(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewerCapacityPolicy]:
        return self.db.execute(
            select(FrameworkReviewerCapacityPolicy)
            .where(FrameworkReviewerCapacityPolicy.organization_id == organization_id)
            .order_by(FrameworkReviewerCapacityPolicy.created_at.desc())
        ).scalars().all()

    def list_latest_workload_snapshots(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewerWorkloadSnapshot]:
        rows = self.db.execute(
            select(FrameworkReviewerWorkloadSnapshot)
            .where(FrameworkReviewerWorkloadSnapshot.organization_id == organization_id)
            .order_by(
                FrameworkReviewerWorkloadSnapshot.user_id.asc(),
                FrameworkReviewerWorkloadSnapshot.calculated_at.desc(),
                FrameworkReviewerWorkloadSnapshot.created_at.desc(),
            )
        ).scalars().all()
        latest_by_user: dict[uuid.UUID, FrameworkReviewerWorkloadSnapshot] = {}
        for row in rows:
            if row.user_id not in latest_by_user:
                latest_by_user[row.user_id] = row
        return list(latest_by_user.values())

    def get_assignment_suggestion(self, suggestion_id: uuid.UUID) -> FrameworkReviewAssignmentSuggestion | None:
        return self.db.execute(
            select(FrameworkReviewAssignmentSuggestion).where(FrameworkReviewAssignmentSuggestion.id == suggestion_id)
        ).scalar_one_or_none()

    def list_assignment_suggestions_for_review(
        self,
        *,
        organization_id: uuid.UUID,
        review_run_id: uuid.UUID,
    ) -> list[FrameworkReviewAssignmentSuggestion]:
        return self.db.execute(
            select(FrameworkReviewAssignmentSuggestion)
            .where(
                FrameworkReviewAssignmentSuggestion.organization_id == organization_id,
                FrameworkReviewAssignmentSuggestion.review_run_id == review_run_id,
            )
            .order_by(FrameworkReviewAssignmentSuggestion.rank.asc(), FrameworkReviewAssignmentSuggestion.created_at.desc())
        ).scalars().all()
