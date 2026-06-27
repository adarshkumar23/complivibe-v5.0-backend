import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DPIACreate(BaseModel):
    processing_activity_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    nature_of_processing: str | None = None
    necessity_assessment: str | None = None
    proportionality_assessment: str | None = None
    risks_identified: list[str] = Field(default_factory=list)
    risk_assessment_notes: str | None = None
    mitigation_measures: list[str] = Field(default_factory=list)
    residual_risk_level: str | None = None
    dpo_consulted: bool = False
    dpo_opinion: str | None = None
    supervisory_authority_consulted: bool = False
    sa_consultation_notes: str | None = None
    next_review_date: date | None = None


class DPIAUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    nature_of_processing: str | None = None
    necessity_assessment: str | None = None
    proportionality_assessment: str | None = None
    risks_identified: list[str] | None = None
    risk_assessment_notes: str | None = None
    mitigation_measures: list[str] | None = None
    residual_risk_level: str | None = None
    dpo_consulted: bool | None = None
    dpo_opinion: str | None = None
    supervisory_authority_consulted: bool | None = None
    sa_consultation_notes: str | None = None
    next_review_date: date | None = None


class DPIAChecklistResponseItem(BaseModel):
    criterion_key: str
    response: str
    notes: str | None = None


class DPIAChecklistRespondRequest(BaseModel):
    responses: list[DPIAChecklistResponseItem]


class DPIASubmitForReviewRequest(BaseModel):
    reviewer_id: uuid.UUID


class DPIARejectRequest(BaseModel):
    notes: str


class DPIAApproveRequest(BaseModel):
    notes: str | None = None


class DPIAChecklistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    dpia_id: uuid.UUID
    criterion_key: str
    question: str
    response: str | None
    notes: str | None
    order_index: int
    created_at: datetime
    updated_at: datetime


class DPIARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    processing_activity_id: uuid.UUID
    title: str
    status: str
    nature_of_processing: str | None
    necessity_assessment: str | None
    proportionality_assessment: str | None
    risks_identified: list
    risk_assessment_notes: str | None
    mitigation_measures: list
    residual_risk_level: str | None
    dpo_consulted: bool
    dpo_opinion: str | None
    supervisory_authority_consulted: bool
    sa_consultation_notes: str | None
    assigned_reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    next_review_date: date | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    checklist_items: list[DPIAChecklistItemRead] = Field(default_factory=list)


class DPIASummaryRead(BaseModel):
    total: int
    by_status: dict[str, int]
    by_residual_risk: dict[str, int]
    approved_count: int
    required_but_missing: int
