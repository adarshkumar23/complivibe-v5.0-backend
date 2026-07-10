import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConnectorCreate(BaseModel):
    connector_type: str
    display_name: str = Field(min_length=1, max_length=255)
    provider_config_json: dict = Field(default_factory=dict)


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    connector_type: str
    display_name: str
    status: str
    provider_config_json: dict
    auto_apply_deterministic_mappings: bool
    expected_event_interval_hours: int
    last_event_received_at: datetime | None
    consecutive_error_count: int
    last_error_message: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConnectorCreateResponse(BaseModel):
    connector: ConnectorRead
    signing_secret: str | None = None
    signing_secret_note: str = (
        "Shown once at creation only. GCP connectors have no signing_secret — GCP push "
        "auth uses a Google-signed OIDC bearer token instead."
    )


class ConnectorHealthRead(BaseModel):
    expected_event_interval_hours: int
    hours_since_last_event: int | None
    is_stale: bool
    context_flags: list[str]


class ConnectorSetupRead(BaseModel):
    connector_type: str
    webhook_url: str
    signing_secret: str | None
    provider_setup_steps: list[dict]


class FindingSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    connector_event_id: uuid.UUID
    evidence_item_id: uuid.UUID
    suggested_control_id: uuid.UUID
    confidence: str
    rationale: str
    status: str
    applied_at: datetime | None
    dismissed_at: datetime | None
    dismissal_reason: str | None


class DismissSuggestionRequest(BaseModel):
    reason: str = Field(min_length=1)
