import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GuardrailCreate(BaseModel):
    ai_system_id: uuid.UUID | None = None
    guardrail_type: str
    constraint_description: str = Field(min_length=1)
    constraint_value: dict
    violation_action: str = "alert_only"


class GuardrailUpdate(BaseModel):
    ai_system_id: uuid.UUID | None = None
    guardrail_type: str | None = None
    constraint_description: str | None = None
    constraint_value: dict | None = None
    violation_action: str | None = None


class GuardrailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID | None
    guardrail_type: str
    constraint_description: str
    constraint_value: dict
    violation_action: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class GuardrailCheckRequest(BaseModel):
    action_context: dict


class GuardrailCheckResult(BaseModel):
    decision: str
    violations: list[str]
    guardrails_checked: int
    blocked: bool


class GuardrailEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    guardrail_id: uuid.UUID
    ai_system_id: uuid.UUID | None
    event_type: str
    context_json: dict
    created_at: datetime


class ApprovalEnvelopeCreate(BaseModel):
    transition_from: str
    transition_to: str
    required_approvers: list[uuid.UUID] = Field(default_factory=list)
    conditions: list = Field(default_factory=list)


class ApprovalEnvelopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    transition_from: str
    transition_to: str
    required_approvers: list[str]
    approvals_received: dict
    conditions: list
    status: str
    expires_at: datetime
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    required_approver_count: int = 0
    approvals_count: int = 0
    approval_progress_pct: float = 0.0
    pending_approver_ids: list[str] = Field(default_factory=list)
    rejected_approver_ids: list[str] = Field(default_factory=list)
    system_deployment_status: str | None = None
    stale_pending: bool = False
    has_context_drift: bool = False
    context_flags: list[str] = Field(default_factory=list)


class EnvelopeDecisionRequest(BaseModel):
    notes: str | None = None


class EnvelopeRejectRequest(BaseModel):
    notes: str = Field(min_length=1)
