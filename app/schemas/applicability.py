from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

APPLICABILITY_CAVEAT = (
    "This is a deterministic applicability suggestion based on questionnaire answers and configured rules. "
    "It is not legal advice or a final regulatory determination."
)


class ApplicabilityAnswerItem(BaseModel):
    question_id: UUID
    answer_value_json: dict | list | str | int | float | bool | None = None
    answer_text: str | None = None
    metadata_json: dict | None = None


class ApplicabilityAnswerSubmitRequest(BaseModel):
    answers: list[ApplicabilityAnswerItem] = Field(min_length=1)


class OrganizationApplicabilityAnswerRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID
    question_id: UUID
    answer_value_json: dict | list | str | int | float | bool | None = None
    answer_text: str | None = None
    status: str
    answered_by_user_id: UUID | None = None
    answered_at: datetime
    superseded_at: datetime | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ObligationApplicabilityRuleCreate(BaseModel):
    question_id: UUID | None = None
    rule_key: str = Field(min_length=1, max_length=128)
    operator: str
    expected_value_json: dict | list | str | int | float | bool | None = None
    result_applicability: str
    rationale: str = Field(min_length=1)


class ObligationApplicabilityRuleRead(BaseModel):
    id: UUID
    framework_id: UUID
    obligation_id: UUID
    question_id: UUID | None = None
    rule_key: str
    operator: str
    expected_value_json: dict | list | str | int | float | bool | None = None
    result_applicability: str
    rationale: str
    status: str
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ApplicabilityEvaluateRequest(BaseModel):
    dry_run: bool = True
    update_obligation_states: bool = False


class ApplicabilityEvaluationResultRead(BaseModel):
    id: UUID | None = None
    organization_id: UUID
    evaluation_run_id: UUID | None = None
    framework_id: UUID
    obligation_id: UUID
    suggested_applicability: str
    previous_applicability: str | None = None
    state_updated: bool = False
    matched_rules_json: list | dict | None = None
    missing_answers_json: list | dict | None = None
    rationale: str
    context_flags: list[str] = Field(default_factory=list)
    provenance_json: dict | None = None
    created_at: datetime | None = None


class ApplicabilityEvaluationRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID
    dry_run: bool
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    evaluated_obligations_count: int
    applicable_count: int
    not_applicable_count: int
    needs_review_count: int
    unknown_count: int
    states_updated_count: int
    summary_json: dict | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime


class ApplicabilityEvaluationRunDetail(BaseModel):
    run: ApplicabilityEvaluationRunRead
    results: list[ApplicabilityEvaluationResultRead]
    caveat: str = APPLICABILITY_CAVEAT


class ApplicabilityEvaluationResponse(BaseModel):
    run: ApplicabilityEvaluationRunRead | None = None
    results: list[ApplicabilityEvaluationResultRead]
    dry_run: bool
    caveat: str = APPLICABILITY_CAVEAT


class ObligationApplicabilityStatusResponse(BaseModel):
    obligation_id: UUID
    framework_id: UUID
    organization_applicability: str | None = None
    suggested_applicability: str | None = None
    matched_rules_json: list | dict | None = None
    missing_answers_json: list | dict | None = None
    provenance_json: dict | None = None
    caveat: str = APPLICABILITY_CAVEAT


class ApplicabilitySummaryResponse(BaseModel):
    total_questions: int
    answered_questions: int
    unanswered_questions: int
    required_questions_count: int = 0
    answered_required_questions: int = 0
    unanswered_required_questions: int = 0
    answer_completion_pct: float = 0
    total_obligations: int
    applicable_obligations: int
    not_applicable_obligations: int
    needs_review_obligations: int
    unknown_obligations: int
    latest_evaluation_at: datetime | None = None
    latest_answer_at: datetime | None = None
    latest_rule_or_question_change_at: datetime | None = None
    stale_answers_count: int = 0
    answers_stale_since_latest_change: bool = False
    caveat: str = APPLICABILITY_CAVEAT
