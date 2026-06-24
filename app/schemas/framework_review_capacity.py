from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FrameworkReviewerCapacityPolicyCreateRequest(BaseModel):
    name: str
    role_name: str | None = None
    max_active_assignments: int
    max_overdue_assignments: int
    preferred_review_types_json: list[str] | None = None
    preferred_target_coverage_levels_json: list[str] | None = None
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class FrameworkReviewerCapacityPolicyUpdateRequest(BaseModel):
    name: str | None = None
    role_name: str | None = None
    max_active_assignments: int | None = None
    max_overdue_assignments: int | None = None
    preferred_review_types_json: list[str] | None = None
    preferred_target_coverage_levels_json: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class FrameworkReviewerCapacityPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    role_name: str | None = None
    max_active_assignments: int
    max_overdue_assignments: int
    preferred_review_types_json: list[str] | None = None
    preferred_target_coverage_levels_json: list[str] | None = None
    status: str
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkReviewerWorkloadCalculateRequest(BaseModel):
    persist: bool = False


class FrameworkReviewAssignmentSuggestionGenerateRequest(BaseModel):
    persist: bool = True
    limit: int = Field(default=5, ge=1, le=50)


class FrameworkReviewAssignmentSuggestionApplyRequest(BaseModel):
    due_at: datetime | None = None
    notes: str | None = None


class FrameworkReviewAssignmentSuggestionDismissRequest(BaseModel):
    dismissal_reason: str


class FrameworkReviewerWorkloadSnapshotRead(BaseModel):
    id: UUID | None = None
    organization_id: UUID
    user_id: UUID
    role_name: str
    active_assignments: int
    accepted_assignments: int
    overdue_assignments: int
    completed_assignments_last_30d: int
    open_escalations: int
    workload_score: int
    capacity_remaining: int | None = None
    snapshot_json: dict
    calculated_at: datetime
    created_at: datetime | None = None


class FrameworkReviewerWorkloadCalculateResponse(BaseModel):
    persist: bool
    count: int
    snapshots: list[FrameworkReviewerWorkloadSnapshotRead]


class FrameworkReviewAssignmentSuggestionRead(BaseModel):
    id: UUID
    organization_id: UUID
    review_run_id: UUID
    suggested_user_id: UUID
    score: int
    rank: int
    status: str
    rationale: str
    scoring_json: dict
    generated_by_user_id: UUID | None = None
    generated_at: datetime
    applied_by_user_id: UUID | None = None
    applied_at: datetime | None = None
    created_assignment_id: UUID | None = None
    dismissed_by_user_id: UUID | None = None
    dismissed_at: datetime | None = None
    dismissal_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkReviewAssignmentSuggestionGeneratedItem(BaseModel):
    id: UUID | None = None
    organization_id: UUID
    review_run_id: UUID
    suggested_user_id: UUID
    score: int
    rank: int
    status: str
    rationale: str
    scoring_json: dict
    generated_by_user_id: UUID | None = None
    generated_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FrameworkReviewAssignmentSuggestionGenerateResponse(BaseModel):
    persist: bool
    limit: int
    count: int
    suggestions: list[FrameworkReviewAssignmentSuggestionGeneratedItem]


class FrameworkReviewCapacitySummaryRead(BaseModel):
    active_reviewers: int
    overloaded_reviewers: int
    reviewers_with_overdue_assignments: int
    total_open_assignments: int
    total_open_escalations: int
    average_workload_score: float
    open_assignment_suggestions: int
    applied_assignment_suggestions: int


class FrameworkReviewerCapacitySimulationPolicyRequest(BaseModel):
    role_name: str | None = None
    max_active_assignments: int
    max_overdue_assignments: int
    preferred_review_types_json: list[str] | None = None
    preferred_target_coverage_levels_json: list[str] | None = None
    review_type: str | None = None
    target_coverage_level: str | None = None


class FrameworkReviewerCapacitySimulationSummary(BaseModel):
    active_reviewers: int
    overloaded_reviewers: int
    reviewers_with_overdue_assignments: int
    total_open_assignments: int
    total_open_escalations: int
    average_workload_score: float


class FrameworkReviewerCapacitySimulationComparison(BaseModel):
    user_id: UUID
    role_name: str
    current_workload_score: int
    simulated_workload_score: int
    delta: int
    reason: str
    current_capacity_remaining: int | None = None
    simulated_capacity_remaining: int | None = None
    active_assignments: int
    overdue_assignments: int
    open_escalations: int
    current_scoring_json: dict
    simulated_scoring_json: dict
    provenance: str


class FrameworkReviewerCapacitySimulationResponse(BaseModel):
    current_summary: FrameworkReviewerCapacitySimulationSummary
    simulated_summary: FrameworkReviewerCapacitySimulationSummary
    reviewer_comparisons: list[FrameworkReviewerCapacitySimulationComparison]
    scoring_formula: dict
    provenance: str
    caveat: str


class FrameworkReviewAssignmentSuggestionSimulationPolicyInput(BaseModel):
    role_name: str | None = None
    max_active_assignments: int
    max_overdue_assignments: int
    preferred_review_types_json: list[str] | None = None
    preferred_target_coverage_levels_json: list[str] | None = None


class FrameworkReviewAssignmentSuggestionSimulateRequest(BaseModel):
    proposed_policy_json: FrameworkReviewAssignmentSuggestionSimulationPolicyInput | None = None
    limit: int = Field(default=5, ge=1, le=50)


class FrameworkReviewAssignmentSuggestionSimulateResponse(BaseModel):
    review_id: UUID
    proposed_policy_used: dict | None = None
    simulated_suggestions: list[FrameworkReviewAssignmentSuggestionGeneratedItem]
    scoring_formula: dict
    provenance: str
    caveat: str


class FrameworkReviewCapacitySimulationSummaryRead(BaseModel):
    simulations_last_24h: int
    simulations_last_7d: int
    caveat: str


class FrameworkReviewWaveSimulationPolicyInput(BaseModel):
    role_name: str | None = None
    max_active_assignments: int
    max_overdue_assignments: int
    preferred_review_types_json: list[str] | None = None
    preferred_target_coverage_levels_json: list[str] | None = None


class FrameworkReviewWaveSimulationRequest(BaseModel):
    framework_id: UUID | None = None
    review_ids: list[UUID] | None = None
    review_type: str | None = None
    target_coverage_level: str | None = None
    max_waves: int = Field(default=3, ge=1, le=20)
    max_reviews_per_wave: int = Field(default=10, ge=1, le=200)
    proposed_policy_json: FrameworkReviewWaveSimulationPolicyInput | None = None
    limit_reviewers: list[UUID] | None = None
    include_existing_assignments: bool = True


class FrameworkReviewWavePlannedReview(BaseModel):
    review_id: UUID
    framework_id: UUID
    review_type: str
    target_coverage_level: str
    suggested_reviewer_id: UUID
    score: int
    rank: int
    rationale: str
    scoring_json: dict


class FrameworkReviewWaveUnassignedReview(BaseModel):
    review_id: UUID
    reason: str
    candidate_count: int
    constraints_failed: list[str]


class FrameworkReviewWaveReviewerProjection(BaseModel):
    user_id: UUID
    role_name: str
    active_assignments: int
    overdue_assignments: int
    open_escalations: int
    completed_assignments_last_30d: int
    workload_score: int
    capacity_remaining: int | None = None
    provenance: str


class FrameworkReviewWaveResult(BaseModel):
    wave_number: int
    planned_reviews: list[FrameworkReviewWavePlannedReview]
    reviewer_projection_after_wave: list[FrameworkReviewWaveReviewerProjection]
    unassigned_in_wave: list[FrameworkReviewWaveUnassignedReview]
    rationale: str


class FrameworkReviewWaveSimulationResponse(BaseModel):
    simulation_id: str
    selected_reviews_count: int
    waves: list[FrameworkReviewWaveResult]
    unassigned_reviews: list[FrameworkReviewWaveUnassignedReview]
    reviewer_load_projection: list[FrameworkReviewWaveReviewerProjection]
    scoring_formula: dict
    constraints_applied: dict
    provenance: str
    caveat: str


class FrameworkReviewBatchAssignmentPlanItem(BaseModel):
    review_run_id: UUID
    assigned_to_user_id: UUID
    due_at: datetime | None = None
    notes: str | None = None


class FrameworkReviewBatchAssignmentValidateRequest(BaseModel):
    assignments: list[FrameworkReviewBatchAssignmentPlanItem] | None = None
    wave_simulation_payload: FrameworkReviewWaveSimulationRequest | None = None
    notify_assignees: bool = False


class FrameworkReviewBatchAssignmentApplyRequest(BaseModel):
    plan_hash: str = Field(min_length=64, max_length=64)
    confirmation_text: str
    assignments: list[FrameworkReviewBatchAssignmentPlanItem] | None = None
    wave_simulation_payload: FrameworkReviewWaveSimulationRequest | None = None
    notify_assignees: bool = False


class FrameworkReviewBatchAssignmentCancelRequest(BaseModel):
    cancellation_reason: str = Field(min_length=3, max_length=2000)


class FrameworkReviewBatchAssignmentCancellationRequestCreateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class FrameworkReviewBatchAssignmentCancellationRequestRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=3, max_length=2000)


class FrameworkReviewBatchAssignmentCancellationRequirementUpdateRequest(BaseModel):
    enabled: bool


class FrameworkReviewBatchAssignmentValidationResponse(BaseModel):
    valid: bool
    plan_hash: str
    required_confirmation_text: str
    total_items: int
    valid_items: int
    invalid_items: int
    warnings: list[str]
    validation_report: dict
    caveat: str


class FrameworkReviewBatchAssignmentApplyResponse(BaseModel):
    run_id: UUID
    status: str
    plan_hash: str
    required_confirmation_text: str
    total_items: int
    created_assignments_count: int
    skipped_items_count: int
    failed_items_count: int
    notify_assignees: bool
    result: dict
    caveat: str


class FrameworkReviewBatchAssignmentRunItemRead(BaseModel):
    id: UUID
    organization_id: UUID
    batch_run_id: UUID
    review_run_id: UUID
    assigned_to_user_id: UUID
    status: str
    created_assignment_id: UUID | None = None
    skipped_reason: str | None = None
    error_message: str | None = None
    scoring_json: dict | None = None
    rationale: str | None = None
    created_at: datetime


class FrameworkReviewBatchAssignmentRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    status: str
    plan_hash: str
    confirmation_text: str
    requested_by_user_id: UUID
    applied_by_user_id: UUID | None = None
    applied_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    cancellation_metadata_json: dict | None = None
    cancellation_requires_approval: bool = False
    cancellation_request_id: UUID | None = None
    total_items: int
    created_assignments_count: int
    skipped_items_count: int
    failed_items_count: int
    notify_assignees: bool
    validation_report_json: dict
    result_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkReviewBatchAssignmentRunDetailRead(FrameworkReviewBatchAssignmentRunRead):
    items: list[FrameworkReviewBatchAssignmentRunItemRead]


class FrameworkReviewBatchAssignmentSummaryRead(BaseModel):
    total_batch_runs: int
    applied_batch_runs: int
    failed_batch_runs: int
    cancelled_batch_runs: int
    assignments_created_last_30d: int
    skipped_duplicates_last_30d: int
    failed_items_last_30d: int


class FrameworkReviewBatchCancellationRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    batch_run_id: UUID
    status: str
    reason: str
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
