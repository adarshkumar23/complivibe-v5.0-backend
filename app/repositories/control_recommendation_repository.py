import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.obligation_control_recommendation import ObligationControlRecommendation
from app.models.recommendation_generation_run import RecommendationGenerationRun


class ControlRecommendationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_recommendation(self, recommendation_id: uuid.UUID) -> ObligationControlRecommendation | None:
        return self.db.execute(
            select(ObligationControlRecommendation).where(ObligationControlRecommendation.id == recommendation_id)
        ).scalar_one_or_none()

    def list_recommendations(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID | None,
        obligation_id: uuid.UUID | None,
        recommendation_type: str | None,
        priority: str | None,
        status: str | None,
        source: str | None,
        limit: int,
        offset: int,
    ) -> list[ObligationControlRecommendation]:
        stmt = select(ObligationControlRecommendation).where(ObligationControlRecommendation.organization_id == organization_id)
        if framework_id is not None:
            stmt = stmt.where(ObligationControlRecommendation.framework_id == framework_id)
        if obligation_id is not None:
            stmt = stmt.where(ObligationControlRecommendation.obligation_id == obligation_id)
        if recommendation_type:
            stmt = stmt.where(ObligationControlRecommendation.recommendation_type == recommendation_type)
        if priority:
            stmt = stmt.where(ObligationControlRecommendation.priority == priority)
        if status:
            stmt = stmt.where(ObligationControlRecommendation.status == status)
        if source:
            stmt = stmt.where(ObligationControlRecommendation.source == source)

        stmt = stmt.order_by(ObligationControlRecommendation.generated_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def find_open_duplicate(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        obligation_id: uuid.UUID,
        recommendation_type: str,
        suggestion_id: uuid.UUID | None,
        existing_control_id: uuid.UUID | None,
    ) -> ObligationControlRecommendation | None:
        stmt = select(ObligationControlRecommendation).where(
            ObligationControlRecommendation.organization_id == organization_id,
            ObligationControlRecommendation.framework_id == framework_id,
            ObligationControlRecommendation.obligation_id == obligation_id,
            ObligationControlRecommendation.recommendation_type == recommendation_type,
            ObligationControlRecommendation.status == "open",
        )
        if suggestion_id is None:
            stmt = stmt.where(ObligationControlRecommendation.suggestion_id.is_(None))
        else:
            stmt = stmt.where(ObligationControlRecommendation.suggestion_id == suggestion_id)

        if existing_control_id is None:
            stmt = stmt.where(ObligationControlRecommendation.existing_control_id.is_(None))
        else:
            stmt = stmt.where(ObligationControlRecommendation.existing_control_id == existing_control_id)

        return self.db.execute(stmt).scalars().first()

    def list_runs(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[RecommendationGenerationRun]:
        stmt = select(RecommendationGenerationRun).where(RecommendationGenerationRun.organization_id == organization_id)
        if framework_id is not None:
            stmt = stmt.where(RecommendationGenerationRun.framework_id == framework_id)
        if status:
            stmt = stmt.where(RecommendationGenerationRun.status == status)
        stmt = stmt.order_by(RecommendationGenerationRun.started_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        now = datetime.now(UTC)
        last_30d = now - timedelta(days=30)

        def _count(stmt) -> int:
            return int(self.db.execute(stmt).scalar_one())

        open_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "open",
            )
        )
        applied_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "applied",
            )
        )
        dismissed_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "dismissed",
            )
        )
        critical_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "open",
                ObligationControlRecommendation.priority == "critical",
            )
        )
        high_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "open",
                ObligationControlRecommendation.priority == "high",
            )
        )
        create_control_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "open",
                ObligationControlRecommendation.recommendation_type.in_(["create_control", "map_existing_control", "review_existing_control"]),
            )
        )
        evidence_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "open",
                ObligationControlRecommendation.recommendation_type.in_(["add_evidence", "refresh_evidence"]),
            )
        )
        applicability_review_recommendations = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.status == "open",
                ObligationControlRecommendation.recommendation_type == "review_applicability",
            )
        )
        recommendations_generated_last_30d = _count(
            select(func.count(ObligationControlRecommendation.id)).where(
                ObligationControlRecommendation.organization_id == organization_id,
                ObligationControlRecommendation.generated_at >= last_30d,
            )
        )

        return {
            "open_recommendations": open_recommendations,
            "applied_recommendations": applied_recommendations,
            "dismissed_recommendations": dismissed_recommendations,
            "critical_recommendations": critical_recommendations,
            "high_recommendations": high_recommendations,
            "create_control_recommendations": create_control_recommendations,
            "evidence_recommendations": evidence_recommendations,
            "applicability_review_recommendations": applicability_review_recommendations,
            "recommendations_generated_last_30d": recommendations_generated_last_30d,
        }
