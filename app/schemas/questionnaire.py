from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

TEMPLATE_TYPE_PATTERN = "^(sig_lite|caiq|custom)$"
QUESTION_TYPE_PATTERN = "^(yes_no|multiple_choice|text|numeric)$"
RESPONSE_STATUS_PATTERN = "^(draft|sent|in_progress|submitted|under_review|completed|expired)$"
CONDITION_OPERATOR_PATTERN = "^(eq|ne|contains|not_contains|gte|lte)$"
INBOUND_SESSION_STATUS_PATTERN = "^(draft|in_progress|under_review|completed|archived)$"
INBOUND_ITEM_STATUS_PATTERN = "^(pending|drafted|needs_review|approved|rejected|sent)$"
INBOUND_ITEM_QUESTION_TYPE_PATTERN = "^(yes_no|text|multiple_choice|numeric)$"
INBOUND_SOURCE_TYPE_PATTERN = "^(evidence|control|certification|policy|previous_answer)$"


class QuestionnaireTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(default="1.0", min_length=1, max_length=50)
    description: str | None = None


class QuestionnaireTemplateCloneRequest(BaseModel):
    new_name: str = Field(min_length=1, max_length=255)


class QuestionnaireTemplateSectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    order_index: int = 0


class QuestionnaireTemplateQuestionCreate(BaseModel):
    question_text: str = Field(min_length=1)
    question_type: str = Field(pattern=QUESTION_TYPE_PATTERN)
    category_tag: str = Field(min_length=1, max_length=100)
    framework_ref: str | None = Field(default=None, max_length=255)
    allowed_values: list[str] | None = None
    expected_answer: str | None = Field(default=None, max_length=255)
    is_required: bool = True
    order_index: int = 0
    help_text: str | None = None


class QuestionnaireTemplateSectionRead(BaseModel):
    id: UUID
    template_id: UUID
    title: str
    description: str | None = None
    order_index: int
    created_at: datetime


class QuestionnaireTemplateQuestionRead(BaseModel):
    id: UUID
    template_id: UUID
    section_id: UUID
    question_text: str
    question_type: str = Field(pattern=QUESTION_TYPE_PATTERN)
    category_tag: str
    framework_ref: str | None = None
    allowed_values: list[str] | None = None
    expected_answer: str | None = None
    is_required: bool
    order_index: int
    help_text: str | None = None
    created_at: datetime


class QuestionnaireTemplateRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    template_type: str = Field(pattern=TEMPLATE_TYPE_PATTERN)
    name: str
    version: str
    description: str | None = None
    is_system_template: bool
    is_active: bool
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class QuestionnaireTemplateDetailRead(QuestionnaireTemplateRead):
    sections: list[QuestionnaireTemplateSectionRead]
    questions: list[QuestionnaireTemplateQuestionRead]


class VendorQuestionnaireResponseCreate(BaseModel):
    vendor_id: UUID
    template_id: UUID
    title: str | None = Field(default=None, max_length=255)
    due_date: date | None = None


class VendorQuestionnaireResponseRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID
    template_id: UUID
    title: str
    status: str = Field(pattern=RESPONSE_STATUS_PATTERN)
    sent_at: datetime | None = None
    due_date: date | None = None
    responded_at: datetime | None = None
    completed_at: datetime | None = None
    calculated_risk_score: int | None = None
    score_computed_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class VendorQuestionnaireAnswerRead(BaseModel):
    id: UUID
    organization_id: UUID
    response_id: UUID
    question_id: UUID
    answer_text: str | None = None
    answer_value: str | None = None
    score_contribution: int | None = None
    is_answered: bool
    created_at: datetime
    updated_at: datetime
    question_text: str | None = None
    category_tag: str | None = None


class VendorQuestionnaireResponseDetailRead(VendorQuestionnaireResponseRead):
    answers: list[VendorQuestionnaireAnswerRead]


class VendorQuestionnaireAnswerSubmit(BaseModel):
    question_id: UUID
    answer_text: str | None = None
    answer_value: str | None = Field(default=None, max_length=255)


class VendorQuestionnaireBulkAnswerSubmit(BaseModel):
    answers: list[VendorQuestionnaireAnswerSubmit]


class VendorQuestionnaireBulkSubmitResult(BaseModel):
    updated: int
    score: int


class VendorQuestionnaireTransitionRequest(BaseModel):
    new_status: str = Field(pattern=RESPONSE_STATUS_PATTERN)


class QuestionnaireRuleCreate(BaseModel):
    template_id: UUID
    question_id: UUID
    rule_name: str = Field(min_length=1, max_length=255)
    condition_operator: str = Field(pattern=CONDITION_OPERATOR_PATTERN)
    condition_value: str = Field(min_length=1, max_length=255)
    score_delta: int
    rationale: str | None = None


class QuestionnaireRuleUpdate(BaseModel):
    rule_name: str | None = Field(default=None, min_length=1, max_length=255)
    condition_operator: str | None = Field(default=None, pattern=CONDITION_OPERATOR_PATTERN)
    condition_value: str | None = Field(default=None, min_length=1, max_length=255)
    score_delta: int | None = None
    rationale: str | None = None
    is_active: bool | None = None


class QuestionnaireRuleRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    template_id: UUID
    question_id: UUID
    rule_name: str
    condition_operator: str = Field(pattern=CONDITION_OPERATOR_PATTERN)
    condition_value: str
    score_delta: int
    rationale: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ScoreBreakdownRuleRead(BaseModel):
    rule_name: str
    score_delta: int
    rationale: str | None = None


class ScoreBreakdownItemRead(BaseModel):
    question_id: UUID
    question_text: str
    category_tag: str
    answer_value: str | None = None
    score_contribution: int
    rules_matched: list[ScoreBreakdownRuleRead]


class ScoreBreakdownUnansweredRead(BaseModel):
    question_id: UUID
    question_text: str


class ScoreBreakdownRead(BaseModel):
    total_score: int
    score_computed_at: datetime | None = None
    total_questions: int
    answered_questions: int
    breakdown: list[ScoreBreakdownItemRead]
    unanswered: list[ScoreBreakdownUnansweredRead]


class VendorQuestionnaireRiskAggregate(BaseModel):
    vendor_id: UUID
    latest_score: int | None = None
    average_score: int | None = None
    response_count: int
    highest_risk_score: int | None = None
    latest_response_id: UUID | None = None


class InboundQuestionnaireSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    sender_name: str = Field(min_length=1, max_length=255)
    sender_email: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_date: date | None = None


class InboundQuestionnaireSessionRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    sender_name: str
    sender_email: str
    description: str | None = None
    due_date: date | None = None
    status: str = Field(pattern=INBOUND_SESSION_STATUS_PATTERN)
    total_questions: int
    drafted_count: int
    approved_count: int
    sent_count: int
    completed_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class InboundQuestionnaireItemCreate(BaseModel):
    question_text: str = Field(min_length=1)
    question_type: str = Field(default="text", pattern=INBOUND_ITEM_QUESTION_TYPE_PATTERN)
    category_tag: str | None = Field(default=None, max_length=100)
    framework_ref: str | None = Field(default=None, max_length=255)
    order_index: int = 0


class InboundQuestionnaireBulkItemCreate(BaseModel):
    items: list[InboundQuestionnaireItemCreate]


class InboundQuestionnaireItemRead(BaseModel):
    id: UUID
    organization_id: UUID
    session_id: UUID
    question_text: str
    question_type: str = Field(pattern=INBOUND_ITEM_QUESTION_TYPE_PATTERN)
    category_tag: str | None = None
    framework_ref: str | None = None
    order_index: int
    suggested_answer_text: str | None = None
    source_type: str | None = Field(default=None, pattern=INBOUND_SOURCE_TYPE_PATTERN)
    source_id: UUID | None = None
    source_title: str | None = None
    source_excerpt: str | None = None
    source_date: date | None = None
    confidence_score: int | None = None
    confidence_reason: str | None = None
    requires_human_review: bool
    status: str = Field(pattern=INBOUND_ITEM_STATUS_PATTERN)
    final_answer_text: str | None = None
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class InboundQuestionnaireBulkAddResult(BaseModel):
    added: int
    session_id: UUID


class InboundQuestionnaireDraftAllResult(BaseModel):
    drafted: int
    needs_review: int
    no_source: int
    session_id: UUID


class InboundQuestionnaireReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|edit|reject)$")
    edited_answer: str | None = None
    review_notes: str | None = None


class InboundQuestionnaireSessionSummary(BaseModel):
    total_questions: int
    drafted_count: int
    approved_count: int
    sent_count: int
    needs_review_count: int
    avg_confidence_score: int
    high_confidence_items: int
    low_confidence_items: int
    source_type_distribution: dict[str, int]


class InboundQuestionnaireResponseTimeMetricsRead(BaseModel):
    session_id: UUID | None = None
    avg_response_time_hours: float | None = None
    median_response_time_hours: float | None = None
    fastest_response_time_hours: float | None = None
    slowest_response_time_hours: float | None = None
    sessions_analyzed: int
    sessions_still_pending: int
