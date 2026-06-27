import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.questionnaire_scoring_rule import QuestionnaireScoringRule
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.vendor_questionnaire_answer import VendorQuestionnaireAnswer
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.services.audit_service import AuditService


class QuestionnaireScoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def require_response_in_org(self, org_id: uuid.UUID, response_id: uuid.UUID) -> VendorQuestionnaireResponse:
        row = self.db.execute(
            select(VendorQuestionnaireResponse).where(
                VendorQuestionnaireResponse.organization_id == org_id,
                VendorQuestionnaireResponse.id == response_id,
                VendorQuestionnaireResponse.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire response not found")
        return row

    def _effective_rules_by_question(
        self,
        org_id: uuid.UUID,
        question_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[QuestionnaireScoringRule]]:
        if not question_ids:
            return {}

        rows = self.db.execute(
            select(QuestionnaireScoringRule).where(
                QuestionnaireScoringRule.question_id.in_(question_ids),
                QuestionnaireScoringRule.is_active.is_(True),
                (QuestionnaireScoringRule.organization_id == org_id) | QuestionnaireScoringRule.organization_id.is_(None),
            )
        ).scalars().all()

        grouped_org: dict[uuid.UUID, list[QuestionnaireScoringRule]] = defaultdict(list)
        grouped_system: dict[uuid.UUID, list[QuestionnaireScoringRule]] = defaultdict(list)
        for row in rows:
            if row.organization_id == org_id:
                grouped_org[row.question_id].append(row)
            else:
                grouped_system[row.question_id].append(row)

        effective: dict[uuid.UUID, list[QuestionnaireScoringRule]] = {}
        for q_id in question_ids:
            if grouped_org.get(q_id):
                effective[q_id] = grouped_org[q_id]
            elif grouped_system.get(q_id):
                effective[q_id] = grouped_system[q_id]
            else:
                effective[q_id] = []
        return effective

    @staticmethod
    def _matches_rule(answer_value: str | None, rule: QuestionnaireScoringRule) -> bool:
        value = (answer_value or "").strip()
        condition = (rule.condition_value or "").strip()

        if rule.condition_operator == "eq":
            return value == condition
        if rule.condition_operator == "ne":
            return value != condition
        if rule.condition_operator == "contains":
            return condition in value
        if rule.condition_operator == "not_contains":
            return condition not in value
        if rule.condition_operator == "gte":
            try:
                return float(value) >= float(condition)
            except ValueError:
                return False
        if rule.condition_operator == "lte":
            try:
                return float(value) <= float(condition)
            except ValueError:
                return False
        return False

    def compute_response_score(
        self,
        org_id: uuid.UUID,
        response_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> int:
        response = self.require_response_in_org(org_id, response_id)
        answers = self.db.execute(
            select(VendorQuestionnaireAnswer).where(
                VendorQuestionnaireAnswer.organization_id == org_id,
                VendorQuestionnaireAnswer.response_id == response_id,
            )
        ).scalars().all()

        answered = [row for row in answers if row.is_answered]
        effective_rules = self._effective_rules_by_question(org_id, [row.question_id for row in answered])

        raw_score = 0
        for row in answers:
            if not row.is_answered:
                row.score_contribution = None
                continue

            contribution = 0
            for rule in effective_rules.get(row.question_id, []):
                if self._matches_rule(row.answer_value, rule):
                    contribution += int(rule.score_delta)

            row.score_contribution = contribution
            raw_score += contribution

        final_score = max(0, min(100, int(raw_score)))
        response.calculated_risk_score = final_score
        response.score_computed_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="questionnaire_response.score_computed",
            entity_type="vendor_questionnaire_response",
            entity_id=response.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "response_id": str(response.id),
                "raw_score": int(raw_score),
                "calculated_risk_score": final_score,
                "score_computed_at": response.score_computed_at.isoformat() if response.score_computed_at else None,
            },
            metadata_json={"source": "api"},
        )
        return final_score

    def get_score_breakdown(self, org_id: uuid.UUID, response_id: uuid.UUID) -> dict:
        response = self.require_response_in_org(org_id, response_id)
        pairs = self.db.execute(
            select(VendorQuestionnaireAnswer, QuestionnaireTemplateQuestion).join(
                QuestionnaireTemplateQuestion,
                QuestionnaireTemplateQuestion.id == VendorQuestionnaireAnswer.question_id,
            ).where(
                VendorQuestionnaireAnswer.organization_id == org_id,
                VendorQuestionnaireAnswer.response_id == response_id,
            )
        ).all()

        total_questions = len(pairs)
        answered_pairs = [(a, q) for a, q in pairs if a.is_answered]
        unanswered_pairs = [(a, q) for a, q in pairs if not a.is_answered]
        effective_rules = self._effective_rules_by_question(org_id, [a.question_id for a, _ in answered_pairs])

        breakdown: list[dict] = []
        for answer, question in answered_pairs:
            matched_rules: list[dict] = []
            contribution = 0
            for rule in effective_rules.get(answer.question_id, []):
                if self._matches_rule(answer.answer_value, rule):
                    contribution += int(rule.score_delta)
                    matched_rules.append(
                        {
                            "rule_name": rule.rule_name,
                            "score_delta": int(rule.score_delta),
                            "rationale": rule.rationale,
                        }
                    )

            breakdown.append(
                {
                    "question_id": question.id,
                    "question_text": question.question_text,
                    "category_tag": question.category_tag,
                    "answer_value": answer.answer_value,
                    "score_contribution": int(answer.score_contribution if answer.score_contribution is not None else contribution),
                    "rules_matched": matched_rules,
                }
            )

        unanswered = [
            {
                "question_id": question.id,
                "question_text": question.question_text,
            }
            for _, question in unanswered_pairs
        ]

        return {
            "total_score": int(response.calculated_risk_score or 0),
            "score_computed_at": response.score_computed_at,
            "total_questions": total_questions,
            "answered_questions": len(answered_pairs),
            "breakdown": breakdown,
            "unanswered": unanswered,
        }

    def recalculate_on_answer(
        self,
        org_id: uuid.UUID,
        response_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> int:
        return self.compute_response_score(org_id, response_id, actor_user_id=actor_user_id)

    def get_vendor_risk_score_from_questionnaires(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(VendorQuestionnaireResponse).where(
                VendorQuestionnaireResponse.organization_id == org_id,
                VendorQuestionnaireResponse.vendor_id == vendor_id,
                VendorQuestionnaireResponse.status == "completed",
                VendorQuestionnaireResponse.deleted_at.is_(None),
                VendorQuestionnaireResponse.calculated_risk_score.is_not(None),
            ).order_by(VendorQuestionnaireResponse.completed_at.desc(), VendorQuestionnaireResponse.updated_at.desc())
        ).scalars().all()

        if not rows:
            return {
                "vendor_id": vendor_id,
                "latest_score": None,
                "average_score": None,
                "response_count": 0,
                "highest_risk_score": None,
                "latest_response_id": None,
            }

        scores = [int(row.calculated_risk_score or 0) for row in rows]
        latest = rows[0]
        return {
            "vendor_id": vendor_id,
            "latest_score": scores[0],
            "average_score": int(round(sum(scores) / len(scores))),
            "response_count": len(rows),
            "highest_risk_score": max(scores),
            "latest_response_id": latest.id,
        }
