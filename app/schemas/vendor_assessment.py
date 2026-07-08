from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

ASSESSMENT_TYPE_PATTERN = "^(initial|periodic|triggered|offboarding)$"
ASSESSMENT_STATUS_PATTERN = "^(draft|in_progress|under_review|completed|cancelled)$"
ASSESSMENT_RATING_PATTERN = "^(satisfactory|needs_improvement|unsatisfactory|not_rated)$"
QUESTION_CATEGORY_PATTERN = "^(security|privacy|compliance|operational|financial|other)$"
QUESTION_RESPONSE_STATUS_PATTERN = "^(not_answered|answered|not_applicable)$"


class VendorAssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    assessment_type: str = Field(pattern=ASSESSMENT_TYPE_PATTERN)
    assigned_to_user_id: UUID | None = None
    due_date: date | None = None
    findings_summary: str | None = None
    overall_rating: str = Field(default="not_rated", pattern=ASSESSMENT_RATING_PATTERN)
    notes: str | None = None
    tags_json: dict | list | None = None


class VendorAssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    assessment_type: str | None = Field(default=None, pattern=ASSESSMENT_TYPE_PATTERN)
    status: str | None = Field(default=None, pattern=ASSESSMENT_STATUS_PATTERN)
    assigned_to_user_id: UUID | None = None
    due_date: date | None = None
    findings_summary: str | None = None
    overall_rating: str | None = Field(default=None, pattern=ASSESSMENT_RATING_PATTERN)
    notes: str | None = None
    tags_json: dict | list | None = None


class VendorAssessmentCancelRequest(BaseModel):
    cancellation_reason: str = Field(min_length=1, max_length=2000)


class VendorAssessmentCompleteRequest(BaseModel):
    overall_rating: str | None = Field(default=None, pattern=ASSESSMENT_RATING_PATTERN)
    findings_summary: str | None = None


class VendorAssessmentRead(UUIDTimestampSchema):
    organization_id: UUID
    vendor_id: UUID
    title: str
    assessment_type: str
    status: str
    assigned_to_user_id: UUID | None = None
    due_date: date | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    findings_summary: str | None = None
    overall_rating: str
    notes: str | None = None
    tags_json: dict | list | None = None
    created_by_user_id: UUID
    is_overdue: bool = False
    risk_id: UUID | None = None


class VendorAssessmentSummary(BaseModel):
    total_assessments: int
    active_assessments: int
    completed_assessments: int
    cancelled_assessments: int
    by_status: dict[str, int]
    by_assessment_type: dict[str, int]
    by_overall_rating: dict[str, int]


class VendorAssessmentQuestionCreate(BaseModel):
    question_text: str = Field(min_length=1, max_length=500)
    question_category: str = Field(pattern=QUESTION_CATEGORY_PATTERN)
    response_text: str | None = None
    response_status: str = Field(default="not_answered", pattern=QUESTION_RESPONSE_STATUS_PATTERN)
    sort_order: int = Field(default=0, ge=0)


class VendorAssessmentQuestionUpdate(BaseModel):
    question_text: str | None = Field(default=None, min_length=1, max_length=500)
    question_category: str | None = Field(default=None, pattern=QUESTION_CATEGORY_PATTERN)
    response_text: str | None = None
    response_status: str | None = Field(default=None, pattern=QUESTION_RESPONSE_STATUS_PATTERN)
    sort_order: int | None = Field(default=None, ge=0)


class VendorAssessmentQuestionAnswerRequest(BaseModel):
    response_text: str = Field(min_length=1)


class VendorAssessmentQuestionRead(UUIDTimestampSchema):
    organization_id: UUID
    assessment_id: UUID
    question_text: str
    question_category: str
    response_text: str | None = None
    response_status: str
    answered_by_user_id: UUID | None = None
    answered_at: datetime | None = None
    sort_order: int
