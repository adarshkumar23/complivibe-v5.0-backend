from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

EVENT_TYPE_PATTERN = r"^(control\.failed|risk\.critical|evidence\.expired|deadline\.overdue|issue\.created|alert\.triggered)$"
WEBHOOK_STATUS_PATTERN = "^(pending|delivered|failed|skipped)$"


class WebhookEndpointCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=255)
    secret: str = Field(min_length=1, max_length=255)
    event_types: list[str] = Field(default_factory=list)


class WebhookEndpointUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    secret: str | None = Field(default=None, min_length=1, max_length=255)
    event_types: list[str] | None = None


class WebhookEndpointRead(BaseModel):
    id: UUID
    organization_id: UUID
    url: str
    name: str
    secret: str
    event_types: list[str]
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class WebhookDeliveryRead(BaseModel):
    id: UUID
    organization_id: UUID
    endpoint_id: UUID
    event_type: str
    payload: dict
    payload_hash: str
    signature: str | None = None
    status: str = Field(pattern=WEBHOOK_STATUS_PATTERN)
    attempts: int
    last_attempted_at: datetime | None = None
    response_code: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookTestEmitRequest(BaseModel):
    event_type: str = Field(pattern=EVENT_TYPE_PATTERN)
    test_payload: dict = Field(default_factory=dict)


class WebhookEventTypesRead(BaseModel):
    event_types: list[str]
