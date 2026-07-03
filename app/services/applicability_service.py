import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.applicability_evaluation_result import ApplicabilityEvaluationResult
from app.models.applicability_evaluation_run import ApplicabilityEvaluationRun
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from app.models.organization_applicability_answer import OrganizationApplicabilityAnswer
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.repositories.applicability_repository import ApplicabilityRepository
from app.core.validation import validate_choice

ALLOWED_RULE_OPERATORS = {
    "equals",
    "not_equals",
    "is_true",
    "is_false",
    "contains",
    "not_contains",
    "in",
    "not_in",
    "exists",
    "not_exists",
}
ALLOWED_RESULT_APPLICABILITY = {"applicable", "not_applicable", "needs_review", "unknown"}
ALLOWED_RULE_STATUS = {"active", "inactive", "archived"}


class ApplicabilityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ApplicabilityRepository(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def validate_operator(operator: str) -> None:
        operator = validate_choice(operator, ALLOWED_RULE_OPERATORS, "operator", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_result_applicability(value: str) -> None:
        value = validate_choice(value, ALLOWED_RESULT_APPLICABILITY, "result_applicability", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def evaluate_operator(operator: str, answer_value: Any, expected_value: Any) -> bool:
        if operator == "equals":
            return answer_value == expected_value
        if operator == "not_equals":
            return answer_value != expected_value
        if operator == "is_true":
            return bool(answer_value) is True
        if operator == "is_false":
            return bool(answer_value) is False
        if operator == "contains":
            if isinstance(answer_value, (list, str)):
                return expected_value in answer_value
            return False
        if operator == "not_contains":
            if isinstance(answer_value, (list, str)):
                return expected_value not in answer_value
            return True
        if operator == "in":
            if isinstance(expected_value, list):
                return answer_value in expected_value
            return False
        if operator == "not_in":
            if isinstance(expected_value, list):
                return answer_value not in expected_value
            return False
        if operator == "exists":
            return answer_value is not None
        if operator == "not_exists":
            return answer_value is None
        return False

    def require_framework(self, framework_id: uuid.UUID) -> Framework:
        row = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
        return row

    def ensure_framework_active_for_org(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.framework_id == framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Framework is not active for organization")

    def _question_or_400(self, *, framework_id: uuid.UUID, question_id: uuid.UUID) -> ObligationApplicabilityQuestion:
        q = self.db.execute(select(ObligationApplicabilityQuestion).where(ObligationApplicabilityQuestion.id == question_id)).scalar_one_or_none()
        if q is None or q.framework_id != framework_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid question_id for framework")
        return q

    def submit_answers(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        answers: list[dict],
        actor_user_id: uuid.UUID,
    ) -> list[OrganizationApplicabilityAnswer]:
        self.require_framework(framework_id)
        self.ensure_framework_active_for_org(organization_id=organization_id, framework_id=framework_id)

        rows: list[OrganizationApplicabilityAnswer] = []
        now = self.now()
        for answer in answers:
            question_id = answer["question_id"]
            self._question_or_400(framework_id=framework_id, question_id=question_id)

            existing = self.repo.active_answer_for_question(
                organization_id=organization_id,
                framework_id=framework_id,
                question_id=question_id,
            )
            if existing is not None:
                existing.status = "superseded"
                existing.superseded_at = now

            row = OrganizationApplicabilityAnswer(
                organization_id=organization_id,
                framework_id=framework_id,
                question_id=question_id,
                answer_value_json=answer.get("answer_value_json"),
                answer_text=answer.get("answer_text"),
                status="active",
                answered_by_user_id=actor_user_id,
                answered_at=now,
                metadata_json=answer.get("metadata_json"),
            )
            self.db.add(row)
            self.db.flush()
            rows.append(row)

        return rows

    def create_rule(
        self,
        *,
        framework_id: uuid.UUID,
        obligation_id: uuid.UUID,
        question_id: uuid.UUID | None,
        rule_key: str,
        operator: str,
        expected_value_json: Any,
        result_applicability: str,
        rationale: str,
        created_by_user_id: uuid.UUID,
    ) -> ObligationApplicabilityRule:
        self.validate_operator(operator)
        self.validate_result_applicability(result_applicability)

        obligation = self.db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
        if obligation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
        if obligation.framework_id != framework_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Obligation does not belong to framework")

        if question_id is not None:
            question = self._question_or_400(framework_id=framework_id, question_id=question_id)
            if question.obligation_id is not None and question.obligation_id != obligation_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="question_id is bound to another obligation")

        row = ObligationApplicabilityRule(
            framework_id=framework_id,
            obligation_id=obligation_id,
            question_id=question_id,
            rule_key=rule_key,
            operator=operator,
            expected_value_json=expected_value_json,
            result_applicability=result_applicability,
            rationale=rationale,
            status="active",
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def archive_rule(self, *, obligation_id: uuid.UUID, rule_id: uuid.UUID) -> ObligationApplicabilityRule:
        row = self.repo.get_rule(rule_id)
        if row is None or row.obligation_id != obligation_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Applicability rule not found")
        if row.status == "archived":
            return row
        row.status = "archived"
        self.db.flush()
        return row

    def evaluate_framework(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        dry_run: bool,
        update_obligation_states: bool,
    ) -> tuple[ApplicabilityEvaluationRun | None, list[dict], dict]:
        self.require_framework(framework_id)
        self.ensure_framework_active_for_org(organization_id=organization_id, framework_id=framework_id)

        obligations = self.db.execute(
            select(Obligation).where(
                Obligation.framework_id == framework_id,
                Obligation.status == "active",
            ).order_by(Obligation.reference_code.asc())
        ).scalars().all()

        answers = self.repo.list_answers(
            organization_id=organization_id,
            framework_id=framework_id,
            active_only=True,
            question_id=None,
        )
        answer_map: dict[uuid.UUID, OrganizationApplicabilityAnswer] = {a.question_id: a for a in answers}

        rules = self.repo.list_rules_for_framework(framework_id=framework_id, active_only=True)
        rules_by_obligation: dict[uuid.UUID, list[ObligationApplicabilityRule]] = {}
        for rule in rules:
            rules_by_obligation.setdefault(rule.obligation_id, []).append(rule)

        run_row: ApplicabilityEvaluationRun | None = None
        now = self.now()
        if not dry_run:
            run_row = ApplicabilityEvaluationRun(
                organization_id=organization_id,
                framework_id=framework_id,
                dry_run=False,
                status="running",
                started_at=now,
                created_by_user_id=actor_user_id,
                created_at=now,
            )
            self.db.add(run_row)
            self.db.flush()

        results_payload: list[dict] = []
        counts = {
            "evaluated_obligations_count": 0,
            "applicable_count": 0,
            "not_applicable_count": 0,
            "needs_review_count": 0,
            "unknown_count": 0,
            "states_updated_count": 0,
        }

        for obligation in obligations:
            obligation_rules = rules_by_obligation.get(obligation.id, [])
            matched_rules: list[dict] = []
            missing_answers: list[dict] = []
            outcomes: list[str] = []
            rationale = ""

            if not obligation_rules:
                suggested = "unknown"
                rationale = "No active applicability rule configured."
            else:
                for rule in obligation_rules:
                    answer_value = None
                    question_row = None
                    if rule.question_id is not None:
                        question_row = self._question_or_400(framework_id=framework_id, question_id=rule.question_id)
                        answer = answer_map.get(rule.question_id)
                        if answer is None:
                            missing_answers.append({
                                "rule_id": str(rule.id),
                                "question_id": str(rule.question_id),
                                "question_key": question_row.question_key,
                            })
                            continue
                        answer_value = answer.answer_value_json

                    matched = self.evaluate_operator(rule.operator, answer_value, rule.expected_value_json)
                    if matched:
                        outcomes.append(rule.result_applicability)
                        matched_rules.append(
                            {
                                "rule_id": str(rule.id),
                                "rule_key": rule.rule_key,
                                "result_applicability": rule.result_applicability,
                                "question_id": str(rule.question_id) if rule.question_id else None,
                            }
                        )

                if missing_answers:
                    suggested = "unknown"
                    rationale = "Missing answers for one or more required rule questions."
                elif not outcomes:
                    suggested = "unknown"
                    rationale = "No rule matched with current answers."
                else:
                    unique = set(outcomes)
                    if "needs_review" in unique:
                        suggested = "needs_review"
                        rationale = "At least one matched rule requires review."
                    elif len(unique) > 1:
                        suggested = "needs_review"
                        rationale = "Conflicting matched rule outcomes require review."
                    else:
                        suggested = outcomes[0]
                        rationale = "All matched rules agree on suggested applicability."

            prev_state = self.db.execute(
                select(OrganizationObligationState).where(
                    OrganizationObligationState.organization_id == organization_id,
                    OrganizationObligationState.obligation_id == obligation.id,
                )
            ).scalar_one_or_none()
            previous_applicability = prev_state.applicability_status if prev_state else None
            state_updated = False

            if not dry_run and update_obligation_states:
                if prev_state is None:
                    prev_state = OrganizationObligationState(
                        organization_id=organization_id,
                        obligation_id=obligation.id,
                        applicability_status=suggested if suggested in {"applicable", "not_applicable", "needs_review", "pending"} else "needs_review",
                        implementation_status="not_started",
                        justification="Suggested by deterministic applicability evaluation.",
                    )
                    self.db.add(prev_state)
                    state_updated = True
                else:
                    target = suggested if suggested in {"applicable", "not_applicable", "needs_review", "pending"} else "needs_review"
                    if prev_state.applicability_status != target:
                        prev_state.applicability_status = target
                        state_updated = True

                if state_updated:
                    counts["states_updated_count"] += 1

            result_payload = {
                "organization_id": organization_id,
                "evaluation_run_id": run_row.id if run_row else None,
                "framework_id": framework_id,
                "obligation_id": obligation.id,
                "suggested_applicability": suggested,
                "previous_applicability": previous_applicability,
                "state_updated": state_updated,
                "matched_rules_json": matched_rules,
                "missing_answers_json": missing_answers,
                "rationale": rationale,
                "provenance_json": {
                    "rule_count": len(obligation_rules),
                    "matched_rule_count": len(matched_rules),
                    "missing_answer_count": len(missing_answers),
                    "answer_snapshot_at": now.isoformat(),
                },
                "created_at": now,
            }
            results_payload.append(result_payload)

            if not dry_run and run_row is not None:
                self.db.add(
                    ApplicabilityEvaluationResult(
                        organization_id=organization_id,
                        evaluation_run_id=run_row.id,
                        framework_id=framework_id,
                        obligation_id=obligation.id,
                        suggested_applicability=suggested,
                        previous_applicability=previous_applicability,
                        state_updated=state_updated,
                        matched_rules_json=matched_rules,
                        missing_answers_json=missing_answers,
                        rationale=rationale,
                        provenance_json=result_payload["provenance_json"],
                        created_at=now,
                    )
                )

            counts["evaluated_obligations_count"] += 1
            counts[f"{suggested}_count"] = counts.get(f"{suggested}_count", 0) + 1

        summary = {
            **counts,
            "framework_id": str(framework_id),
            "organization_id": str(organization_id),
            "dry_run": dry_run,
            "update_obligation_states": (update_obligation_states and not dry_run),
        }

        if not dry_run and run_row is not None:
            run_row.status = "completed"
            run_row.finished_at = self.now()
            run_row.evaluated_obligations_count = counts["evaluated_obligations_count"]
            run_row.applicable_count = counts["applicable_count"]
            run_row.not_applicable_count = counts["not_applicable_count"]
            run_row.needs_review_count = counts["needs_review_count"]
            run_row.unknown_count = counts["unknown_count"]
            run_row.states_updated_count = counts["states_updated_count"]
            run_row.summary_json = summary
            self.db.flush()

        return run_row, results_payload, summary

    def evaluation_summary(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> dict:
        total_questions = int(
            self.db.execute(
                select(func.count(ObligationApplicabilityQuestion.id)).where(
                    ObligationApplicabilityQuestion.framework_id == framework_id,
                    ObligationApplicabilityQuestion.status == "active",
                )
            ).scalar_one()
        )
        answered_questions = int(
            self.db.execute(
                select(func.count(func.distinct(OrganizationApplicabilityAnswer.question_id))).where(
                    OrganizationApplicabilityAnswer.organization_id == organization_id,
                    OrganizationApplicabilityAnswer.framework_id == framework_id,
                    OrganizationApplicabilityAnswer.status == "active",
                )
            ).scalar_one()
        )

        total_obligations = int(
            self.db.execute(
                select(func.count(Obligation.id)).where(
                    Obligation.framework_id == framework_id,
                    Obligation.status == "active",
                )
            ).scalar_one()
        )

        latest_run = self.db.execute(
            select(ApplicabilityEvaluationRun)
            .where(
                ApplicabilityEvaluationRun.organization_id == organization_id,
                ApplicabilityEvaluationRun.framework_id == framework_id,
            )
            .order_by(ApplicabilityEvaluationRun.started_at.desc())
        ).scalars().first()

        applicable_obligations = latest_run.applicable_count if latest_run else 0
        not_applicable_obligations = latest_run.not_applicable_count if latest_run else 0
        needs_review_obligations = latest_run.needs_review_count if latest_run else 0
        unknown_obligations = latest_run.unknown_count if latest_run else total_obligations

        return {
            "total_questions": total_questions,
            "answered_questions": answered_questions,
            "unanswered_questions": max(0, total_questions - answered_questions),
            "total_obligations": total_obligations,
            "applicable_obligations": applicable_obligations,
            "not_applicable_obligations": not_applicable_obligations,
            "needs_review_obligations": needs_review_obligations,
            "unknown_obligations": unknown_obligations,
            "latest_evaluation_at": latest_run.finished_at if latest_run else None,
        }
