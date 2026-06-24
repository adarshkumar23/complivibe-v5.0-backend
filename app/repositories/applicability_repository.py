import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.applicability_evaluation_result import ApplicabilityEvaluationResult
from app.models.applicability_evaluation_run import ApplicabilityEvaluationRun
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from app.models.organization_applicability_answer import OrganizationApplicabilityAnswer


class ApplicabilityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_answers(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        active_only: bool,
        question_id: uuid.UUID | None,
    ) -> list[OrganizationApplicabilityAnswer]:
        stmt = select(OrganizationApplicabilityAnswer).where(
            OrganizationApplicabilityAnswer.organization_id == organization_id,
            OrganizationApplicabilityAnswer.framework_id == framework_id,
        )
        if active_only:
            stmt = stmt.where(OrganizationApplicabilityAnswer.status == "active")
        if question_id is not None:
            stmt = stmt.where(OrganizationApplicabilityAnswer.question_id == question_id)
        stmt = stmt.order_by(OrganizationApplicabilityAnswer.answered_at.desc())
        return self.db.execute(stmt).scalars().all()

    def active_answer_for_question(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> OrganizationApplicabilityAnswer | None:
        stmt = (
            select(OrganizationApplicabilityAnswer)
            .where(
                OrganizationApplicabilityAnswer.organization_id == organization_id,
                OrganizationApplicabilityAnswer.framework_id == framework_id,
                OrganizationApplicabilityAnswer.question_id == question_id,
                OrganizationApplicabilityAnswer.status == "active",
            )
            .order_by(OrganizationApplicabilityAnswer.answered_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def list_rules_for_obligation(
        self,
        *,
        obligation_id: uuid.UUID,
        active_only: bool = False,
    ) -> list[ObligationApplicabilityRule]:
        stmt = select(ObligationApplicabilityRule).where(ObligationApplicabilityRule.obligation_id == obligation_id)
        if active_only:
            stmt = stmt.where(ObligationApplicabilityRule.status == "active")
        stmt = stmt.order_by(ObligationApplicabilityRule.created_at.asc())
        return self.db.execute(stmt).scalars().all()

    def list_rules_for_framework(self, *, framework_id: uuid.UUID, active_only: bool = True) -> list[ObligationApplicabilityRule]:
        stmt = select(ObligationApplicabilityRule).where(ObligationApplicabilityRule.framework_id == framework_id)
        if active_only:
            stmt = stmt.where(ObligationApplicabilityRule.status == "active")
        stmt = stmt.order_by(ObligationApplicabilityRule.created_at.asc())
        return self.db.execute(stmt).scalars().all()

    def get_rule(self, rule_id: uuid.UUID) -> ObligationApplicabilityRule | None:
        return self.db.execute(select(ObligationApplicabilityRule).where(ObligationApplicabilityRule.id == rule_id)).scalar_one_or_none()

    def get_run(self, run_id: uuid.UUID) -> ApplicabilityEvaluationRun | None:
        return self.db.execute(select(ApplicabilityEvaluationRun).where(ApplicabilityEvaluationRun.id == run_id)).scalar_one_or_none()

    def list_runs(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> list[ApplicabilityEvaluationRun]:
        stmt = (
            select(ApplicabilityEvaluationRun)
            .where(
                ApplicabilityEvaluationRun.organization_id == organization_id,
                ApplicabilityEvaluationRun.framework_id == framework_id,
            )
            .order_by(ApplicabilityEvaluationRun.started_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def list_results_for_run(self, *, organization_id: uuid.UUID, run_id: uuid.UUID) -> list[ApplicabilityEvaluationResult]:
        stmt = (
            select(ApplicabilityEvaluationResult)
            .where(
                ApplicabilityEvaluationResult.organization_id == organization_id,
                ApplicabilityEvaluationResult.evaluation_run_id == run_id,
            )
            .order_by(ApplicabilityEvaluationResult.created_at.asc())
        )
        return self.db.execute(stmt).scalars().all()

    def latest_result_for_obligation(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        obligation_id: uuid.UUID,
    ) -> ApplicabilityEvaluationResult | None:
        stmt = (
            select(ApplicabilityEvaluationResult)
            .where(
                ApplicabilityEvaluationResult.organization_id == organization_id,
                ApplicabilityEvaluationResult.framework_id == framework_id,
                ApplicabilityEvaluationResult.obligation_id == obligation_id,
            )
            .order_by(ApplicabilityEvaluationResult.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()
