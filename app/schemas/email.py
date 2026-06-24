from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class EmailTemplateCreate(BaseModel):
    template_key: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    subject_template: str
    body_text_template: str
    body_html_template: str | None = None
    allowed_variables_json: list[str] = Field(default_factory=list)
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    subject_template: str | None = None
    body_text_template: str | None = None
    body_html_template: str | None = None
    allowed_variables_json: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class EmailTemplateRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    template_key: str
    name: str
    description: str | None = None
    subject_template: str
    body_text_template: str
    body_html_template: str | None = None
    allowed_variables_json: list[str]
    status: str
    version: int
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class EmailTemplatePreviewRequest(BaseModel):
    variables_json: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class EmailTemplatePreviewResponse(BaseModel):
    subject: str
    body_text: str
    body_html: str | None = None


class EmailOutboxCreate(BaseModel):
    template_id: UUID | None = None
    template_key: str | None = None
    recipient_email: EmailStr
    recipient_user_id: UUID | None = None
    event_type: str = Field(min_length=2, max_length=120)
    variables_json: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    scheduled_at: datetime | None = None
    metadata_json: dict | None = None
    initial_status: str = Field(default="pending", pattern="^(draft|pending)$")


class EmailOutboxRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    template_id: UUID | None = None
    event_type: str
    recipient_email: EmailStr
    recipient_user_id: UUID | None = None
    subject: str
    body_text: str
    body_html: str | None = None
    status: str
    priority: str
    scheduled_at: datetime | None = None
    queued_at: datetime
    sent_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    lock_expires_at: datetime | None = None
    last_attempt_at: datetime | None = None
    next_attempt_at: datetime | None = None
    dead_lettered_at: datetime | None = None
    attempt_count: int
    max_attempts: int
    last_error: str | None = None
    provider: str | None = None
    provider_message_id: str | None = None
    metadata_json: dict | None = None
    worker_metadata_json: dict | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class EmailDeliveryEventRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    email_outbox_id: UUID
    event_type: str
    status_from: str | None = None
    status_to: str | None = None
    details_json: dict | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime


class EmailOutboxDetail(EmailOutboxRead):
    delivery_events: list[EmailDeliveryEventRead]


class EmailMarkFailedRequest(BaseModel):
    error_message: str = Field(min_length=3, max_length=2000)


class WorkerClaimRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=10, ge=1, le=200)


class WorkerCompleteRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=120)
    provider_message_id: str | None = Field(default=None, max_length=255)


class WorkerFailRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=120)
    error_message: str = Field(min_length=3, max_length=2000)
    retry_after_seconds: int | None = Field(default=None, ge=1, le=604800)


class WorkerDeadLetterRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class WorkerActionResponse(BaseModel):
    email: EmailOutboxRead


class WorkerReleaseExpiredLocksResponse(BaseModel):
    released_count: int
    emails: list[EmailOutboxRead]
