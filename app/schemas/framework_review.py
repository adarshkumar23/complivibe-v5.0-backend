from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FrameworkPackReviewStartRequest(BaseModel):
    framework_version_id: UUID | None = None
    pack_key: str | None = None
    coverage_report_id: UUID | None = None
    review_type: str = Field(pattern="^(internal_review|expert_review|final_verification)$")
    target_coverage_level: str = Field(pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")
    checklist_json: dict | None = None


class FrameworkPackReviewCompleteRequest(BaseModel):
    outcome: str = Field(pattern="^(pass|fail|needs_changes|not_ready)$")
    checklist_json: dict
    findings_json: dict | None = None
    caveat: str | None = None


class FrameworkPackReviewSignoffCreateRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


class FrameworkPackPromotionCreateRequest(BaseModel):
    review_run_id: UUID
    to_coverage_level: str = Field(pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")


class FrameworkPackPromotionRejectRequest(BaseModel):
    rejection_reason: str


class FrameworkPackPromotionPreflightRequest(BaseModel):
    review_run_id: UUID
    to_coverage_level: str = Field(pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")


class FrameworkPackReviewSignoffRead(BaseModel):
    id: UUID
    organization_id: UUID
    review_run_id: UUID
    signer_user_id: UUID
    signer_role_name: str | None = None
    decision: str
    comment: str | None = None
    signed_at: datetime
    signoff_checksum_sha256: str | None = None
    signoff_signature: str | None = None
    signing_key_id: str | None = None
    signature_algorithm: str | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkPackReviewRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID
    framework_version_id: UUID | None = None
    pack_key: str | None = None
    coverage_report_id: UUID | None = None
    review_type: str
    target_coverage_level: str
    status: str
    started_by_user_id: UUID | None = None
    started_at: datetime
    completed_by_user_id: UUID | None = None
    completed_at: datetime | None = None
    outcome: str | None = None
    checklist_json: dict
    findings_json: dict | None = None
    coverage_snapshot_json: dict
    caveat: str
    created_at: datetime
    updated_at: datetime


class FrameworkPackReviewDetail(BaseModel):
    review: FrameworkPackReviewRunRead
    signoffs: list[FrameworkPackReviewSignoffRead]
    caveat: str


class FrameworkPackPromotionRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID
    framework_version_id: UUID | None = None
    review_run_id: UUID
    from_coverage_level: str
    to_coverage_level: str
    status: str
    requested_by_user_id: UUID
    requested_at: datetime
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    executed_by_user_id: UUID | None = None
    executed_at: datetime | None = None
    execution_result_json: dict | None = None
    created_at: datetime
    updated_at: datetime
    caveat: str


class FrameworkPackPromotionGateResult(BaseModel):
    passed: bool
    gate_failures: list[str]
    from_coverage_level: str
    to_coverage_level: str
    approved_signoffs: int
    review_type: str
    review_outcome: str | None = None
    coverage: dict
    caveat: str


class FrameworkReviewSummaryRead(BaseModel):
    latest_review_status: str | None = None
    latest_review_outcome: str | None = None
    latest_review_type: str | None = None
    approved_signoffs: int
    pending_promotions: int
    executed_promotions: int
    current_coverage_level: str
    promotion_readiness: dict
    caveat: str


class FrameworkPackReviewAssignmentCreateRequest(BaseModel):
    assigned_to_user_id: UUID
    due_at: datetime | None = None
    notes: str | None = None
    notify: bool = False


class FrameworkPackReviewAssignmentCompleteRequest(BaseModel):
    notes: str | None = None


class FrameworkPackReviewAssignmentCancelRequest(BaseModel):
    reason: str


class FrameworkPackReviewAssignmentRead(BaseModel):
    id: UUID
    organization_id: UUID
    review_run_id: UUID
    assigned_to_user_id: UUID
    assigned_by_user_id: UUID
    status: str
    due_at: datetime | None = None
    accepted_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkReviewQueueItem(BaseModel):
    assignment: FrameworkPackReviewAssignmentRead
    review_type: str
    target_coverage_level: str
    framework_id: UUID
    is_overdue: bool


class FrameworkReviewSLAPolicyCreateRequest(BaseModel):
    name: str
    review_type: str = Field(pattern="^(internal_review|expert_review|final_verification)$")
    target_coverage_level: str | None = Field(default=None, pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")
    due_days: int
    escalation_after_days: int
    reminder_before_days: int
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class FrameworkReviewSLAPolicyUpdateRequest(BaseModel):
    name: str | None = None
    review_type: str | None = Field(default=None, pattern="^(internal_review|expert_review|final_verification)$")
    target_coverage_level: str | None = Field(default=None, pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")
    due_days: int | None = None
    escalation_after_days: int | None = None
    reminder_before_days: int | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class FrameworkReviewSLAPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    review_type: str
    target_coverage_level: str | None = None
    due_days: int
    escalation_after_days: int
    reminder_before_days: int
    status: str
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkReviewSLAEvaluateRequest(BaseModel):
    dry_run: bool = True
    notify: bool = False


class FrameworkReviewSLAEvaluateResponse(BaseModel):
    dry_run: bool
    would_create_count: int
    created_count: int
    queued_email_count: int
    would_create: list[dict]
    created_event_ids: list[str]
    queued_email_ids: list[str]


class FrameworkReviewEscalationEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    review_run_id: UUID
    assignment_id: UUID | None = None
    event_type: str
    status: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    details_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkReviewEscalationResolveRequest(BaseModel):
    resolution_notes: str | None = None


class FrameworkReviewQueueSummaryRead(BaseModel):
    total_assignments: int
    open_assignments: int
    accepted_assignments: int
    completed_assignments: int
    overdue_assignments: int
    open_escalations: int
    reviews_waiting_for_signoff: int
    promotions_pending_approval: int
