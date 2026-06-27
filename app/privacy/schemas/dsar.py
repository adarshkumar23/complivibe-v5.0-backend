import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DataSubjectRequestCreate(BaseModel):
    request_type: str
    subject_name: str = Field(min_length=1, max_length=255)
    subject_email: EmailStr
    subject_identifier: str | None = Field(default=None, max_length=500)
    description: str | None = None
    regulatory_framework: str = "gdpr"
    assigned_handler_id: uuid.UUID | None = None
    deadline_days: int | None = Field(default=None, ge=1, le=365)


class PublicDSRSubmit(BaseModel):
    organization_id: uuid.UUID
    request_type: str
    subject_name: str = Field(min_length=1, max_length=255)
    subject_email: EmailStr
    description: str | None = None
    regulatory_framework: str = "gdpr"


class PublicDSRSubmitResponse(BaseModel):
    request_ref: str
    response_deadline: datetime
    message: str


class DataSubjectRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    request_ref: str
    request_type: str
    subject_name: str
    subject_email: str
    subject_identifier: str | None
    description: str | None
    status: str
    regulatory_framework: str
    response_deadline: datetime
    deadline_days: int
    extension_granted: bool
    extension_deadline: datetime | None
    extension_reason: str | None
    identity_verified: bool
    identity_verified_at: datetime | None
    identity_verified_by: uuid.UUID | None
    assigned_handler_id: uuid.UUID | None
    response_notes: str | None
    refusal_reason: str | None
    received_at: datetime
    fulfilled_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class DSRTransitionRequest(BaseModel):
    new_status: str
    notes: str | None = None
    refusal_reason: str | None = None


class DSRAssignRequest(BaseModel):
    handler_id: uuid.UUID


class DSRExtensionRequest(BaseModel):
    reason: str = Field(min_length=3)


class DSRFulfillmentStepCreate(BaseModel):
    step_type: str
    description: str = Field(min_length=1)
    assigned_to: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = None
    order_index: int | None = Field(default=None, ge=0)


class DSRFulfillmentStepUpdate(BaseModel):
    step_type: str | None = None
    description: str | None = None
    status: str | None = None
    assigned_to: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = None
    order_index: int | None = Field(default=None, ge=0)


class DSRFulfillmentStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    request_id: uuid.UUID
    step_type: str
    description: str
    status: str
    assigned_to: uuid.UUID | None
    due_date: date | None
    completed_at: datetime | None
    notes: str | None
    order_index: int
    created_at: datetime
    updated_at: datetime


class DSRSummaryRead(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_framework: dict[str, int]
    overdue_count: int
    avg_days_to_fulfill: float
    sla_compliance_rate: float
