import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.vendor_mitigation_service import VendorMitigationService
from app.models.audit_log import AuditLog
from app.models.questionnaire_scoring_rule import QuestionnaireScoringRule
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.vendor_questionnaire_answer import VendorQuestionnaireAnswer
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.services.audit_service import AuditService


class QuestionnaireScoringService:
    HIGH_RISK_THRESHOLD = 70

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
    def _effective_answer_text(answer: VendorQuestionnaireAnswer) -> str | None:
        """Prefer the documented answer_text field, falling back to answer_value."""
        return answer.answer_text or answer.answer_value

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
            answer_text_for_scoring = self._effective_answer_text(row)
            for rule in effective_rules.get(row.question_id, []):
                if self._matches_rule(answer_text_for_scoring, rule):
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
        self._auto_create_mitigation_case_on_threshold_breach(
            response=response,
            score=final_score,
            actor_user_id=actor_user_id,
        )
        return final_score

    def _top_triggering_answers_summary(self, response: VendorQuestionnaireResponse, *, limit: int = 3) -> str:
        """Summarize the highest-scoring answers that actually drove the breach.

        Without this, every auto-created mitigation case's description is just a
        generic score number -- a reviewer has to go dig up the questionnaire
        response separately to find out *why* the vendor is high-risk.
        """
        pairs = self.db.execute(
            select(VendorQuestionnaireAnswer, QuestionnaireTemplateQuestion)
            .join(QuestionnaireTemplateQuestion, QuestionnaireTemplateQuestion.id == VendorQuestionnaireAnswer.question_id)
            .where(
                VendorQuestionnaireAnswer.organization_id == response.organization_id,
                VendorQuestionnaireAnswer.response_id == response.id,
                VendorQuestionnaireAnswer.score_contribution.is_not(None),
                VendorQuestionnaireAnswer.score_contribution > 0,
            )
            .order_by(VendorQuestionnaireAnswer.score_contribution.desc())
        ).all()
        if not pairs:
            return "No individual answer contributed a positive score (see full response for detail)."

        entries = []
        for answer, question in pairs[:limit]:
            answer_text = self._effective_answer_text(answer) or "(no answer text)"
            entries.append(f'"{question.question_text}" -> "{answer_text}" (+{answer.score_contribution})')
        return "; ".join(entries)

    def _auto_create_mitigation_case_on_threshold_breach(
        self,
        *,
        response: VendorQuestionnaireResponse,
        score: int,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        # Threshold defaults to 70 when no org-configured vendor threshold exists.
        if score < self.HIGH_RISK_THRESHOLD:
            return

        marker = f"[auto_response_id:{response.id}]"
        existing = self.db.execute(
            select(VendorMitigationCase).where(
                VendorMitigationCase.organization_id == response.organization_id,
                VendorMitigationCase.vendor_id == response.vendor_id,
                VendorMitigationCase.deleted_at.is_(None),
                VendorMitigationCase.status.not_in(["closed", "cancelled"]),
                VendorMitigationCase.description.ilike(f"%{marker}%"),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

        # A different response for the same vendor breaching threshold while an
        # auto-created case from a *prior* breach is still open shouldn't spawn a
        # second case for the same underlying vendor risk -- note the repeat breach
        # against the existing case instead of creating a duplicate.
        existing_open_case = self.db.execute(
            select(VendorMitigationCase).where(
                VendorMitigationCase.organization_id == response.organization_id,
                VendorMitigationCase.vendor_id == response.vendor_id,
                VendorMitigationCase.deleted_at.is_(None),
                VendorMitigationCase.status.not_in(["closed", "cancelled"]),
                VendorMitigationCase.description.ilike("%[auto_response_id:%"),
            )
        ).scalar_one_or_none()
        if existing_open_case is not None:
            # An answer-by-answer bulk submission recomputes the score after every
            # single answer, so this branch can be entered repeatedly for the same
            # response as it crosses the threshold multiple times in one submission --
            # only note the repeat breach once per (case, response) pair.
            prior_notes = self.db.execute(
                select(AuditLog.after_json).where(
                    AuditLog.organization_id == response.organization_id,
                    AuditLog.action == "vendor_mitigation.repeat_threshold_breach_noted",
                    AuditLog.entity_id == existing_open_case.id,
                )
            ).scalars().all()
            if any(note.get("questionnaire_response_id") == str(response.id) for note in prior_notes):
                return

            AuditService(self.db).write_audit_log(
                action="vendor_mitigation.repeat_threshold_breach_noted",
                entity_type="vendor_mitigation_case",
                entity_id=existing_open_case.id,
                organization_id=response.organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "vendor_id": str(response.vendor_id),
                    "questionnaire_response_id": str(response.id),
                    "score": int(score),
                    "existing_case_id": str(existing_open_case.id),
                },
                metadata_json={"source": "questionnaire_scoring_hook"},
            )
            return

        vendor = self.db.execute(
            select(Vendor).where(
                Vendor.id == response.vendor_id,
                Vendor.organization_id == response.organization_id,
            )
        ).scalar_one_or_none()
        if vendor is None:
            return

        created_by = actor_user_id or response.created_by

        vendor_assessment = self.db.execute(
            select(VendorAssessment).where(
                VendorAssessment.organization_id == response.organization_id,
                VendorAssessment.vendor_id == response.vendor_id,
                VendorAssessment.status != "cancelled",
            ).order_by(VendorAssessment.created_at.desc())
        ).scalars().first()
        if vendor_assessment is None:
            # A mitigation case must be anchored to a VendorAssessment (DB CHECK constraint).
            # Rather than silently no-op when the vendor has no prior assessment on record,
            # auto-create a minimal "triggered" one anchored to this exact questionnaire
            # response -- the questionnaire response itself already represents completed
            # assessment work, it just wasn't captured as a formal VendorAssessment row.
            vendor_assessment = VendorAssessment(
                organization_id=response.organization_id,
                vendor_id=response.vendor_id,
                title=f"Auto-generated from questionnaire response {response.id}",
                assessment_type="triggered",
                status="completed",
                completed_at=self.utcnow(),
                findings_summary=(
                    f"Auto-generated when questionnaire response {response.id} scored "
                    f"{score}/100, breaching the high-risk threshold of {self.HIGH_RISK_THRESHOLD}, "
                    "with no prior vendor assessment on record for this vendor."
                ),
                created_by_user_id=created_by,
            )
            self.db.add(vendor_assessment)
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="vendor_assessment.auto_created_from_questionnaire",
                entity_type="vendor_assessment",
                entity_id=vendor_assessment.id,
                organization_id=response.organization_id,
                actor_user_id=actor_user_id,
                after_json={"vendor_id": str(response.vendor_id), "response_id": str(response.id)},
                metadata_json={"source": "questionnaire_threshold_breach"},
            )
        triggering_answers_summary = self._top_triggering_answers_summary(response)
        case_payload = SimpleNamespace(
            vendor_id=response.vendor_id,
            assessment_id=vendor_assessment.id,
            ai_assessment_id=None,
            title=f"Auto Mitigation: Questionnaire risk score {score}",
            description=(
                f"Automatically created from questionnaire response threshold breach. "
                f"Response {response.id} scored {score}/{self.HIGH_RISK_THRESHOLD}. "
                f"Top contributing answers: {triggering_answers_summary} {marker}"
            ),
            severity="critical" if score >= 85 else "high",
            assigned_owner_id=vendor.owner_user_id,
            due_date=date.today() + timedelta(days=14),
        )

        row = VendorMitigationService(self.db).create_case(
            response.organization_id,
            case_payload,
            created_by=created_by,
        )
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation.auto_created_threshold_breach",
            entity_type="vendor_mitigation_case",
            entity_id=row.id,
            organization_id=response.organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "vendor_id": str(response.vendor_id),
                "questionnaire_response_id": str(response.id),
                "score": int(score),
                "threshold": self.HIGH_RISK_THRESHOLD,
            },
            metadata_json={"source": "questionnaire_scoring_hook"},
        )

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
            answer_text_for_scoring = self._effective_answer_text(answer)
            for rule in effective_rules.get(answer.question_id, []):
                if self._matches_rule(answer_text_for_scoring, rule):
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
