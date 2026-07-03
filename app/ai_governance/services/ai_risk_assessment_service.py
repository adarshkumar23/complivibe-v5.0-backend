import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.bias_metrics_service import BiasMetricsService
from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_assessment_question import AIRiskAssessmentQuestion
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.ai_system import AISystem
from app.models.risk import Risk
from app.services.audit_service import AuditService

RESPONSE_SCORES = {
    "low_risk": Decimal("1"),
    "medium_risk": Decimal("2"),
    "high_risk": Decimal("3"),
    "critical_risk": Decimal("4"),
}
DIMENSIONS = ["bias", "fairness", "explainability", "privacy", "misuse", "security"]
DIMENSION_WEIGHT = Decimal("0.1666666667")
QUESTION_BANK: list[tuple[str, str]] = [
    # bias
    ("bias", "Does the training data represent all affected demographic groups proportionally?"),
    ("bias", "Has the model been tested for disparate error rates across demographic groups?"),
    ("bias", "Are historical biases in the training data identified and documented?"),
    ("bias", "Is bias testing repeated after any model update or retraining?"),
    ("bias", "Is there a process to receive and investigate bias complaints?"),
    # fairness
    ("fairness", "Does the system produce equal-quality outcomes across protected attributes?"),
    ("fairness", "Have fairness metrics (e.g. demographic parity) been computed and documented?"),
    ("fairness", "Is the fairness threshold for this system defined and agreed with stakeholders?"),
    ("fairness", "Are there counterfactual fairness tests for individual-level decisions?"),
    ("fairness", "Is fairness evaluated periodically in production, not just at deployment?"),
    # explainability
    ("explainability", "Can the system provide a human-readable explanation for its outputs?"),
    ("explainability", "Are explanations available for all high-stakes decisions?"),
    ("explainability", "Do explanations include the most influential features or factors?"),
    ("explainability", "Are explanations validated to be faithful to the model's actual logic?"),
    ("explainability", "Can a non-technical stakeholder understand the explanation?"),
    # privacy
    ("privacy", "Is a Data Protection Impact Assessment (DPIA) completed for this system?"),
    ("privacy", "Does the system process special category personal data (health, ethnicity, biometric)?"),
    ("privacy", "Is data minimization applied - only necessary data is processed?"),
    ("privacy", "Are data retention periods defined and enforced for training and inference data?"),
    ("privacy", "Are data subject rights (access, deletion, objection) implementable for this system?"),
    # misuse
    ("misuse", "Are there documented prohibited uses for this AI system?"),
    ("misuse", "Is access to the system controlled to prevent unauthorized use?"),
    ("misuse", "Could the system be repurposed for surveillance, manipulation, or discrimination?"),
    ("misuse", "Are misuse detection mechanisms in place?"),
    ("misuse", "Is there an incident response process specific to AI misuse events?"),
    # security
    ("security", "Has the system been tested for adversarial attacks (e.g. prompt injection, data poisoning)?"),
    ("security", "Are model weights and training artifacts stored securely with access controls?"),
    ("security", "Is the supply chain for third-party models and datasets verified?"),
    ("security", "Are model inference endpoints protected against denial-of-service attacks?"),
    ("security", "Is model versioning and rollback capability available?"),
]


class AIRiskAssessmentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def _require_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> AIRiskAssessment:
        row = self.db.execute(
            select(AIRiskAssessment).where(
                AIRiskAssessment.id == assessment_id,
                AIRiskAssessment.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk assessment not found")
        return row

    def _question_bank(self) -> list[AIRiskAssessmentQuestion]:
        count = self.db.execute(select(func.count(AIRiskAssessmentQuestion.id))).scalar_one()
        if int(count or 0) == 0:
            for idx, (dimension, text) in enumerate(QUESTION_BANK):
                self.db.add(
                    AIRiskAssessmentQuestion(
                        risk_dimension=dimension,
                        question_text=text,
                        weight=Decimal("1.0"),
                        order_index=idx % 5,
                        is_active=True,
                    )
                )
            self.db.flush()

        rows = self.db.execute(
            select(AIRiskAssessmentQuestion).where(AIRiskAssessmentQuestion.is_active.is_(True)).order_by(
                AIRiskAssessmentQuestion.risk_dimension.asc(),
                AIRiskAssessmentQuestion.order_index.asc(),
                AIRiskAssessmentQuestion.question_text.asc(),
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="AI risk assessment question bank is empty",
            )
        return rows

    def create_assessment(self, org_id: uuid.UUID, system_id: uuid.UUID, created_by: uuid.UUID) -> AIRiskAssessment:
        self._require_system(org_id, system_id)

        max_version = self.db.execute(
            select(func.max(AIRiskAssessment.assessment_version)).where(
                AIRiskAssessment.organization_id == org_id,
                AIRiskAssessment.ai_system_id == system_id,
            )
        ).scalar_one_or_none()
        next_version = int(max_version or 0) + 1

        now = self.utcnow()
        assessment = AIRiskAssessment(
            organization_id=org_id,
            ai_system_id=system_id,
            assessment_version=next_version,
            status="draft",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(assessment)
        self.db.flush()

        questions = self._question_bank()
        for question in questions:
            self.db.add(
                AIRiskAssessmentResponse(
                    organization_id=org_id,
                    assessment_id=assessment.id,
                    question_id=question.id,
                    response=None,
                    notes=None,
                    risk_contribution=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "risk_assessment.created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"assessment_id": str(assessment.id), "assessment_version": next_version},
        )
        AuditService(self.db).write_audit_log(
            action="risk_assessment.created",
            entity_type="ai_risk_assessment",
            entity_id=assessment.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": assessment.status, "assessment_version": next_version},
            metadata_json={"source": "api"},
        )
        return assessment

    def get_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> AIRiskAssessment:
        return self._require_assessment(org_id, assessment_id)

    def list_assessments(
        self,
        org_id: uuid.UUID,
        *,
        system_id: uuid.UUID | None = None,
        status_filter: str | None = None,
    ) -> list[AIRiskAssessment]:
        stmt = select(AIRiskAssessment).where(AIRiskAssessment.organization_id == org_id)
        if system_id is not None:
            stmt = stmt.where(AIRiskAssessment.ai_system_id == system_id)
        if status_filter is not None:
            stmt = stmt.where(AIRiskAssessment.status == status_filter)
        return self.db.execute(stmt.order_by(AIRiskAssessment.created_at.desc())).scalars().all()

    def submit_responses(self, org_id: uuid.UUID, assessment_id: uuid.UUID, responses: list[dict], user_id: uuid.UUID) -> AIRiskAssessment:
        assessment = self._require_assessment(org_id, assessment_id)

        resp_by_question = {
            row.question_id: row
            for row in self.db.execute(
                select(AIRiskAssessmentResponse).where(
                    AIRiskAssessmentResponse.organization_id == org_id,
                    AIRiskAssessmentResponse.assessment_id == assessment_id,
                )
            ).scalars().all()
        }

        for item in responses:
            question_id = uuid.UUID(str(item.get("question_id")))
            response_value = item.get("response")
            notes = item.get("notes")
            if response_value not in RESPONSE_SCORES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid response")
            row = resp_by_question.get(question_id)
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment question response row not found")

            row.response = response_value
            row.notes = notes
            row.risk_contribution = (RESPONSE_SCORES[response_value] / Decimal("4")) * Decimal("100")
            row.updated_at = self.utcnow()

        if assessment.status == "draft":
            assessment.status = "in_progress"
        assessment.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "risk_assessment.responses_submitted",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=assessment.ai_system_id,
            event_data={"assessment_id": str(assessment.id), "response_count": len(responses)},
        )
        AuditService(self.db).write_audit_log(
            action="risk_assessment.responses_submitted",
            entity_type="ai_risk_assessment",
            entity_id=assessment.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": assessment.status},
            metadata_json={"source": "api"},
        )
        return assessment

    def _to_rating(self, score: Decimal) -> str:
        value = float(score)
        if value <= 25:
            return "low"
        if value <= 50:
            return "medium"
        if value <= 75:
            return "high"
        return "critical"

    def complete_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, user_id: uuid.UUID) -> AIRiskAssessment:
        assessment = self._require_assessment(org_id, assessment_id)
        system = self._require_system(org_id, assessment.ai_system_id)

        response_rows = self.db.execute(
            select(AIRiskAssessmentResponse, AIRiskAssessmentQuestion)
            .join(
                AIRiskAssessmentQuestion,
                AIRiskAssessmentQuestion.id == AIRiskAssessmentResponse.question_id,
            )
            .where(
                AIRiskAssessmentResponse.organization_id == org_id,
                AIRiskAssessmentResponse.assessment_id == assessment_id,
            )
        ).all()

        if any(resp.response is None for resp, _question in response_rows):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="All assessment questions must be answered before completion",
            )

        per_dimension_scores: dict[str, list[Decimal]] = defaultdict(list)
        for resp, question in response_rows:
            score = RESPONSE_SCORES.get(str(resp.response), Decimal("0"))
            per_dimension_scores[question.risk_dimension].append(score)

        dimension_results: dict[str, Decimal] = {}
        for dimension in DIMENSIONS:
            values = per_dimension_scores.get(dimension, [])
            if not values:
                dim_score = Decimal("0")
            else:
                avg = sum(values) / Decimal(len(values))
                dim_score = (avg / Decimal("4")) * Decimal("100")
            dimension_results[dimension] = dim_score.quantize(Decimal("0.01"))

        overall_score = sum(dimension_results.values()) * DIMENSION_WEIGHT
        overall_score = max(Decimal("0"), min(Decimal("100"), overall_score)).quantize(Decimal("0.01"))

        assessment.bias_risk_rating = self._to_rating(dimension_results["bias"])
        assessment.fairness_risk_rating = self._to_rating(dimension_results["fairness"])
        assessment.explainability_risk_rating = self._to_rating(dimension_results["explainability"])
        assessment.privacy_risk_rating = self._to_rating(dimension_results["privacy"])
        assessment.misuse_risk_rating = self._to_rating(dimension_results["misuse"])
        assessment.security_risk_rating = self._to_rating(dimension_results["security"])
        assessment.overall_risk_score = overall_score
        assessment.status = "completed"
        assessment.completed_by = user_id
        assessment.completed_at = self.utcnow()
        assessment.updated_at = self.utcnow()

        severity = self._to_rating(overall_score)
        base_scale = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        scaled = base_scale[severity]

        risk = Risk(
            organization_id=org_id,
            title=f"AI Risk: {system.name}",
            description=f"Auto-created from AI risk assessment version {assessment.assessment_version} with score {overall_score}",
            category="other",
            severity=severity,
            likelihood=scaled,
            impact=scaled,
            inherent_score=scaled * scaled,
            composite_score_method="standard",
            status="identified",
            treatment_strategy="undecided",
            owner_user_id=system.owner_id,
            metadata_json={
                "source": "ai_risk_assessment",
                "assessment_id": str(assessment.id),
                "ai_system_id": str(system.id),
                "overall_risk_score": float(overall_score),
            },
            created_by_user_id=user_id,
        )
        self.db.add(risk)
        self.db.flush()
        from app.services.risk_service import RiskService
        RiskService(self.db).check_appetite_breach(organization_id=org_id, risk=risk, actor_user_id=user_id)

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "risk_assessment.completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=assessment.ai_system_id,
            event_data={
                "assessment_id": str(assessment.id),
                "overall_risk_score": float(overall_score),
                "risk_id": str(risk.id),
            },
        )
        AuditService(self.db).write_audit_log(
            action="risk_assessment.completed",
            entity_type="ai_risk_assessment",
            entity_id=assessment.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": assessment.status,
                "overall_risk_score": float(overall_score),
                "risk_id": str(risk.id),
            },
            metadata_json={"source": "api"},
        )
        return assessment

    def compute_bias(
        self,
        org_id: uuid.UUID,
        assessment_id: uuid.UUID,
        predictions: list[int | float],
        protected_attrs: list[int | float],
        labels: list[int | float] | None,
        user_id: uuid.UUID,
    ) -> dict:
        assessment = self._require_assessment(org_id, assessment_id)

        if len(predictions) != len(protected_attrs):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="predictions and protected_attribute_values must be equal length",
            )
        if labels is not None and len(labels) != len(predictions):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="labels length must match predictions",
            )

        metrics = BiasMetricsService.compute_bias_metrics(
            predictions=predictions,
            protected_attribute_values=protected_attrs,
            labels=labels,
        )

        assessment.assessment_bias_results = metrics
        assessment.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "risk_assessment.bias_computed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=assessment.ai_system_id,
            event_data={"assessment_id": str(assessment.id)},
        )
        AuditService(self.db).write_audit_log(
            action="risk_assessment.bias_computed",
            entity_type="ai_risk_assessment",
            entity_id=assessment.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"assessment_bias_results": metrics},
            metadata_json={"source": "api"},
        )
        return metrics
