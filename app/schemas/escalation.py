from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

ENTITY_TYPE_PATTERN = "^(issue|risk|vendor_mitigation|control_exception|pbc_request)$"
CONDITION_TYPE_PATTERN = "^(time_in_state|sla_breach|severity_threshold)$"


class EscalationPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(pattern=ENTITY_TYPE_PATTERN)
    condition_type: str = Field(pattern=CONDITION_TYPE_PATTERN)
    condition_value: dict = Field(default_factory=dict)
    escalate_to_user_id: UUID
    notification_message_template: str = Field(min_length=1)


class EscalationPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    condition_value: dict | None = None
    escalate_to_user_id: UUID | None = None
    notification_message_template: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class EscalationPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    entity_type: str = Field(pattern=ENTITY_TYPE_PATTERN)
    condition_type: str = Field(pattern=CONDITION_TYPE_PATTERN)
    condition_value: dict
    escalate_to_user_id: UUID
    notification_message_template: str
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class EscalationEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    entity_type: str = Field(pattern=ENTITY_TYPE_PATTERN)
    entity_id: UUID
    escalated_at: datetime
    escalated_to: UUID
    notification_sent: bool
    notification_queued_at: datetime | None = None


class EscalationEvaluateResult(BaseModel):
    policies_evaluated: int
    escalations_fired: int
    skipped_idempotent: int
