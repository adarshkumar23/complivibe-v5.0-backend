from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class ComplianceBotSubscriptionCreate(BaseModel):
    platform: str = Field(pattern="^(slack|teams)$")
    channel_ref: str = Field(min_length=1, max_length=255)
    is_active: bool = True
    digest_enabled: bool = True
    digest_time_utc: str = Field(default="08:00", pattern="^[0-2][0-9]:[0-5][0-9]$")
    sla_alerts_enabled: bool = True


class ComplianceBotSubscriptionRead(UUIDTimestampSchema):
    organization_id: UUID
    user_id: UUID
    platform: str
    channel_ref: str
    is_active: bool
    digest_enabled: bool
    digest_time_utc: str
    sla_alerts_enabled: bool
    last_digest_sent_at: datetime | None = None
    last_sla_alert_sent_at: datetime | None = None
    created_by_user_id: UUID | None = None
    context_flags: list[str] = []


class SlackSlashCommandPayload(BaseModel):
    command: str
    text: str = ""
    user_id: str | None = None
    channel_id: str | None = None
    team_id: str | None = None
    response_url: str | None = None
    trigger_id: str | None = None


class TeamsCommandPayload(BaseModel):
    text: str
    service_url: str | None = None
    conversation_id: str | None = None
    from_user_id: str | None = None


class ComplianceBotCommandResponse(BaseModel):
    platform: str
    command: str
    handled: bool
    response_text: str
    state_changed: bool
    details: dict
    replayed: bool = False


class ComplianceBotOutboxRead(UUIDTimestampSchema):
    organization_id: UUID
    subscription_id: UUID
    message_type: str
    status: str
    command_text: str | None = None
    content_text: str
    payload_json: dict
    scheduled_for: datetime
    sent_at: datetime | None = None
    failed_at: datetime | None = None
    error_message: str | None = None
    idempotency_key: str | None = None


class ComplianceBotSweepResult(BaseModel):
    processed_subscriptions: int
    queued_messages: int
    organizations_checked: int
    state_changes: int
    failed_subscriptions: int = 0
