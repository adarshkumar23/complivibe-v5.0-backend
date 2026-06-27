import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AIReviewCreateRequest(BaseModel):
    system_id: uuid.UUID
    review_type: str
    assigned_reviewer_id: uuid.UUID
    due_date: date | None = None


class AIReviewCriteriaResponseItem(BaseModel):
    criterion_key: str
    question: str
    response: str | None
    notes: str | None


class AIReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    review_type: str
    status: str
    assigned_reviewer_id: uuid.UUID
    due_date: date | None
    completed_at: datetime | None
    decision_notes: str | None
    conditions: list[str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class AIReviewWithCriteriaRead(BaseModel):
    review: AIReviewRead
    criteria: list[AIReviewCriteriaResponseItem]


class AIReviewRespondItem(BaseModel):
    criterion_key: str
    response: str | None
    notes: str | None = None


class AIReviewRespondRequest(BaseModel):
    responses: list[AIReviewRespondItem]


class AIReviewApproveRequest(BaseModel):
    decision_notes: str | None = None


class AIReviewRejectRequest(BaseModel):
    decision_notes: str


class AIReviewConditionalRequest(BaseModel):
    conditions: list[str] = Field(default_factory=list)
    decision_notes: str | None = None


class AIReviewCompleteConditionalRequest(BaseModel):
    notes: str | None = None
