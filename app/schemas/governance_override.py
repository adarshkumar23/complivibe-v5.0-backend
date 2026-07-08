from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GovernanceOverrideCreate(BaseModel):
    override_type: str
    target_entity_type: str
    target_entity_id: UUID
    requested_action: str
    reason: str
    required_approvals: int = Field(default=2, ge=2)
    expires_at: datetime | None = None
    metadata_json: dict | None = None


class GovernanceOverrideCreateFromTemplate(BaseModel):
    template_id: UUID
    target_entity_id: UUID
    reason: str
    expires_at: datetime | None = None
    metadata_json: dict | None = None


class GovernanceOverrideDecisionRequest(BaseModel):
    reason: str | None = None


class GovernanceOverrideRejectRequest(BaseModel):
    reason: str


class GovernanceOverrideCancelRequest(BaseModel):
    reason: str


class GovernanceOverrideApprovalRead(BaseModel):
    id: UUID
    organization_id: UUID
    override_request_id: UUID
    approver_user_id: UUID
    decision: str
    reason: str | None = None
    created_at: datetime


class GovernanceOverrideEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    override_request_id: UUID
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    actor_user_id: UUID | None = None
    details_json: dict | None = None
    created_at: datetime


class GovernanceOverrideRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    override_type: str
    target_entity_type: str
    target_entity_id: UUID
    requested_action: str
    reason: str
    status: str
    requested_by_user_id: UUID
    template_id: UUID | None = None
    template_version: int | None = None
    required_approvals: int
    approval_count: int
    rejection_count: int
    expires_at: datetime | None = None
    executed_by_user_id: UUID | None = None
    executed_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    execution_result_json: dict | None = None
    routing_context_json: dict | None = None
    approver_role_names_json: list[str] | None = None
    metadata_json: dict | None = None
    approvals_remaining: int = 0
    decision_count: int = 0
    approval_progress_pct: float = 0
    request_age_hours: float = 0
    expires_in_hours: float | None = None
    is_expired: bool = False
    stale_pending: bool = False
    last_event_at: datetime | None = None
    target_state_changed_since_request: bool = False
    target_entity_missing: bool = False
    context_flags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class GovernanceOverrideEligibleApproverRead(BaseModel):
    user_id: UUID
    role_name: str


class GovernanceOverrideDetail(BaseModel):
    request: GovernanceOverrideRequestRead
    approvals: list[GovernanceOverrideApprovalRead]
    events: list[GovernanceOverrideEventRead]
    eligible_approvers: list[GovernanceOverrideEligibleApproverRead] = []


class GovernanceOverrideRoutingRead(BaseModel):
    override_id: UUID
    template_id: UUID | None = None
    template_version: int | None = None
    required_approvals: int
    approver_role_names_json: list[str] | None = None
    routing_context_json: dict | None = None


class GovernanceOverrideListResponse(BaseModel):
    requests: list[GovernanceOverrideRequestRead]


class GovernanceOverrideExpireResponse(BaseModel):
    expired_count: int


class GovernanceOverrideSummary(BaseModel):
    total_requests: int
    pending_requests: int
    approved_requests: int
    rejected_requests: int
    executed_requests: int
    cancelled_requests: int
    expired_requests: int
    pending_approval_over_24h: int
    overrides_executed_last_30d: int
    pending_expiring_within_24h: int = 0
    approved_awaiting_execution: int = 0
    execution_failed_last_30d: int = 0
    oldest_pending_request_age_hours: float | None = None
    context_flags: list[str] = Field(default_factory=list)


class GovernanceOverrideTemplateBase(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    override_type: str
    target_entity_type: str
    requested_action: str
    default_required_approvals: int = Field(default=2, ge=2)
    approver_role_names_json: list[str] | None = None
    condition_rules_json: list[dict] | None = None
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class GovernanceOverrideTemplateCreate(GovernanceOverrideTemplateBase):
    pass


class GovernanceOverrideTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    override_type: str | None = None
    target_entity_type: str | None = None
    requested_action: str | None = None
    default_required_approvals: int | None = Field(default=None, ge=2)
    approver_role_names_json: list[str] | None = None
    condition_rules_json: list[dict] | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class GovernanceOverrideTemplateRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    override_type: str
    target_entity_type: str
    requested_action: str
    status: str
    default_required_approvals: int
    approver_role_names_json: list[str] | None = None
    condition_rules_json: list[dict] | None = None
    version: int
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class GovernanceOverrideTemplateVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    template_id: UUID
    version: int
    name: str
    description: str | None = None
    override_type: str
    target_entity_type: str
    requested_action: str
    default_required_approvals: int
    approver_role_names_json: list[str] | None = None
    condition_rules_json: list[dict] | None = None
    status: str
    created_by_user_id: UUID | None = None
    created_at: datetime


class GovernanceOverrideTemplateListResponse(BaseModel):
    templates: list[GovernanceOverrideTemplateRead]


class GovernanceOverrideTemplateDetail(BaseModel):
    template: GovernanceOverrideTemplateRead
    latest_version: GovernanceOverrideTemplateVersionRead | None = None


class GovernanceOverrideTemplateSummary(BaseModel):
    total_templates: int
    active_templates: int
    inactive_templates: int
    archived_templates: int
    templates_with_conditional_rules: int
    template_bound_requests_last_30d: int
