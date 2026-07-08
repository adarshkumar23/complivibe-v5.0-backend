from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class EvidenceAutomationRuleCreate(BaseModel):
    trigger_source: str = Field(pattern="^(webhook|email|form)$")
    trigger_config: dict = Field(default_factory=dict)
    target_control_id: UUID | None = None
    evidence_type: str = Field(default="other", min_length=1, max_length=64)
    transform_template: str | None = Field(default=None, max_length=4000)
    is_active: bool = True


class EvidenceAutomationRuleUpdate(BaseModel):
    trigger_config: dict | None = None
    target_control_id: UUID | None = None
    evidence_type: str | None = Field(default=None, min_length=1, max_length=64)
    transform_template: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None


class EvidenceAutomationRuleRead(UUIDTimestampSchema):
    organization_id: UUID
    trigger_source: str
    trigger_config: dict
    target_control_id: UUID | None = None
    evidence_type: str
    transform_template: str | None = None
    is_active: bool
    created_by_user_id: UUID | None = None
    last_triggered_at: datetime | None = None
    last_matched_at: datetime | None = None
    trigger_count: int = 0
    consecutive_error_count: int = 0
    last_error_at: datetime | None = None
    last_error_message: str | None = None
    is_stale: bool = False
    needs_attention: bool = False
    target_control_archived: bool = False
    context_flags: list[str] = []


class EvidenceAutomationIngestPayload(BaseModel):
    payload: dict = Field(default_factory=dict)
    received_at: datetime | None = None


class EvidenceAutomationIngestError(BaseModel):
    rule_id: UUID
    reason: str


class EvidenceAutomationIngestDuplicate(BaseModel):
    rule_id: UUID
    idempotency_key: str


class EvidenceAutomationIngestResponse(BaseModel):
    source: str
    matched_rule_count: int
    skipped_rule_count: int
    created_count: int
    duplicate_count: int = 0
    evidence_item_ids: list[UUID]
    errors: list[EvidenceAutomationIngestError]
    duplicates: list[EvidenceAutomationIngestDuplicate] = []
