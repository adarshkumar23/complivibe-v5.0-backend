from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class IssueSyncConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(pattern="^(jira|linear)$")
    entity_type: str = Field(default="issue", pattern="^issue$")
    direction_mode: str = Field(default="two_way", pattern="^(outbound_only|inbound_only|two_way)$")
    is_active: bool = True
    project_ref: str | None = Field(default=None, max_length=128)
    api_base_url: str | None = None
    credentials_json: dict = Field(default_factory=dict)
    webhook_secret: str | None = Field(default=None, max_length=255)
    field_mapping_json: dict = Field(default_factory=dict)


class IssueSyncConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    direction_mode: str | None = Field(default=None, pattern="^(outbound_only|inbound_only|two_way)$")
    is_active: bool | None = None
    project_ref: str | None = Field(default=None, max_length=128)
    api_base_url: str | None = None
    credentials_json: dict | None = None
    webhook_secret: str | None = Field(default=None, max_length=255)
    field_mapping_json: dict | None = None


class IssueSyncConnectionRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    provider: str
    entity_type: str
    direction_mode: str
    is_active: bool
    project_ref: str | None = None
    api_base_url: str | None = None
    credentials_json: dict
    webhook_secret: str | None = None
    field_mapping_json: dict
    created_by: UUID | None = None


class IssueSyncLinkCreate(BaseModel):
    entity_type: str = Field(default="issue", pattern="^issue$")
    internal_entity_id: UUID
    external_entity_id: str = Field(min_length=1, max_length=255)
    external_key: str | None = Field(default=None, max_length=255)


class IssueSyncLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    connection_id: UUID
    entity_type: str
    internal_entity_id: UUID
    external_entity_id: str
    external_key: str | None = None
    last_synced_at: datetime | None = None
    last_status: str | None = None


class IssueSyncOutboundRequest(BaseModel):
    issue_id: UUID
    include_status: bool = True
    include_comment: bool = False
    comment_body: str | None = None


class IssueSyncWebhookResponse(BaseModel):
    processed: bool
    event_id: UUID
    status: str
    detail: str


class IssueSyncEventRead(UUIDTimestampSchema):
    organization_id: UUID
    connection_id: UUID
    provider: str
    direction: str
    entity_type: str
    event_type: str
    external_event_id: str | None = None
    status: str
    payload_json: dict
    error_message: str | None = None
    processed_at: datetime


class IssueSyncCommentRead(UUIDTimestampSchema):
    organization_id: UUID
    issue_id: UUID
    provider: str
    direction: str
    external_comment_id: str | None = None
    body: str
    author_ref: str | None = None
    created_by_user_id: UUID | None = None
