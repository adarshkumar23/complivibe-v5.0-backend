from datetime import datetime
from datetime import date as date_type
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

SYSTEM_TYPE_PATTERN = "^(internal_model|third_party_model|ai_feature|agent|workflow_automation|other)$"
LIFECYCLE_STATUS_PATTERN = "^(proposed|in_development|testing|production|retired|archived)$"


class AISystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    system_type: str = Field(pattern=SYSTEM_TYPE_PATTERN)
    lifecycle_status: str = Field(default="proposed", pattern=LIFECYCLE_STATUS_PATTERN)
    deployment_environment: str | None = Field(default=None, max_length=64)
    business_owner_user_id: UUID | None = None
    technical_owner_user_id: UUID | None = None
    vendor_name: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=255)
    model_name: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=128)
    intended_purpose: str | None = None
    use_case: str | None = None
    data_categories_json: list[str] | None = None
    user_groups_json: list[str] | None = None
    geography_json: list[str] | None = None
    tags_json: list[str] | None = None
    notes: str | None = None


class AISystemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_type: str | None = Field(default=None, pattern=SYSTEM_TYPE_PATTERN)
    lifecycle_status: str | None = Field(default=None, pattern=LIFECYCLE_STATUS_PATTERN)
    deployment_environment: str | None = Field(default=None, max_length=64)
    business_owner_user_id: UUID | None = None
    technical_owner_user_id: UUID | None = None
    vendor_name: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=255)
    model_name: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=128)
    intended_purpose: str | None = None
    use_case: str | None = None
    data_categories_json: list[str] | None = None
    user_groups_json: list[str] | None = None
    geography_json: list[str] | None = None
    tags_json: list[str] | None = None
    notes: str | None = None


class AISystemArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    system_type: str
    lifecycle_status: str
    deployment_environment: str | None = None
    business_owner_user_id: UUID | None = None
    technical_owner_user_id: UUID | None = None
    vendor_name: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    intended_purpose: str | None = None
    use_case: str | None = None
    data_categories_json: list[str] | None = None
    user_groups_json: list[str] | None = None
    geography_json: list[str] | None = None
    tags_json: list[str] | None = None
    notes: str | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemSummary(BaseModel):
    total_systems: int
    active_systems: int
    archived_systems: int
    by_lifecycle_status: dict[str, int]
    by_system_type: dict[str, int]
    with_business_owner: int
    with_technical_owner: int
    missing_owner_count: int


AI_RISK_ASSESSMENT_TYPE_PATTERN = "^(initial|periodic|material_change|incident_followup|pre_deployment)$"
AI_RISK_ASSESSMENT_STATUS_PATTERN = "^(draft|in_review|completed|archived)$"
AI_RISK_VALUE_PATTERN = "^(unknown|low|medium|high|critical)$"
AI_RISK_SNAPSHOT_TYPE_PATTERN = "^(manual_snapshot|completion_snapshot|archive_snapshot)$"
AI_RISK_SCORING_PROFILE_STATUS_PATTERN = "^(active|inactive|archived)$"
AI_RISK_DIMENSION_TEMPLATE_STATUS_PATTERN = "^(active|inactive|archived)$"
AI_RISK_CLASSIFICATION_TAXONOMY_STATUS_PATTERN = "^(active|inactive|archived)$"
AI_RISK_CLASSIFICATION_STATUS_PATTERN = "^(active|superseded|archived)$"
AI_RISK_CLASSIFICATION_CONFIDENCE_PATTERN = "^(unknown|low|medium|high)$"
AI_RISK_CLASSIFICATION_SOURCE_TYPE_PATTERN = "^(operator_attestation|customer_input|internal_review|external_counsel|other)$"
AI_RISK_CLASSIFICATION_REVIEW_STATUS_PATTERN = "^(not_submitted|in_review|changes_requested|reviewed|rejected)$"
AI_RISK_CLASSIFICATION_SNAPSHOT_TYPE_PATTERN = (
    "^(manual_snapshot|review_snapshot|changes_requested_snapshot|rejection_snapshot|archive_snapshot)$"
)
GOVERNANCE_SIGNAL_DOMAIN_PATTERN = "^(ai_risk)$"
GOVERNANCE_SIGNAL_ENTITY_TYPE_PATTERN = "^(ai_system|risk_assessment|risk_classification)$"
GOVERNANCE_SIGNAL_SEVERITY_PATTERN = "^(info|warning|critical)$"
GOVERNANCE_SIGNAL_STATUS_PATTERN = "^(open|resolved|dismissed|archived)$"
GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN = "^(low|medium|high|urgent)$"
GOVERNANCE_CANDIDATE_ACTION_TYPE_PATTERN = (
    "^(create_record|update_record|review_record|attach_evidence|resolve_issue|create_snapshot|refresh_signals|"
    "prepare_draft|send_reminder)$"
)
GOVERNANCE_RECOMMENDATION_SCOPE_TYPE_PATTERN = "^(organization|ai_system|risk_assessment)$"
GOVERNANCE_RECOMMENDATION_SOURCE_TYPE_PATTERN = "^(candidate_actions)$"
GOVERNANCE_RECOMMENDATION_DISPOSITION_STATUS_PATTERN = (
    "^(acknowledged|dismissed|deferred|accepted_for_manual_work)$"
)
GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN = (
    "^(ai_system_attention_brief|risk_assessment_review_brief|recommendation_snapshot_summary|"
    "classification_review_brief|executive_risk_summary|action_plan_brief)$"
)
GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN = "^(organization|ai_system|risk_assessment|recommendation_snapshot)$"
GOVERNANCE_COPILOT_GENERATION_MODE_PATTERN = "^(deterministic_template)$"
GOVERNANCE_AUTOPILOT_POLICY_STATUS_PATTERN = "^(active|inactive|archived)$"
GOVERNANCE_AUTOPILOT_POLICY_MODE_PATTERN = "^(disabled|observe_only|suggest_only|draft_only|require_approval|execute_safe_later)$"
GOVERNANCE_AUTOPILOT_INTENT_STATUS_PATTERN = "^(planned|approval_required|blocked|archived)$"
GOVERNANCE_AUTOPILOT_INTENT_SOURCE_TYPE_PATTERN = "^(candidate_action|recommendation_snapshot|copilot_draft_snapshot)$"
GOVERNANCE_AUTOPILOT_APPROVAL_STATUS_PATTERN = "^(requested|approved|rejected|cancelled)$"
GOVERNANCE_AUTOPILOT_APPROVAL_POLICY_STATUS_PATTERN = "^(active|inactive|archived)$"
GOVERNANCE_AUTOPILOT_VOTE_STATUS_PATTERN = "^(approved|rejected)$"
GOVERNANCE_AUTOPILOT_READINESS_STATE_PATTERN = "^(not_ready|approval_required|ready_for_runner|blocked|cancelled|rejected)$"
GOVERNANCE_AUTOPILOT_ACTION_RISK_TIER_PATTERN = "^(low|medium|high)$"
GOVERNANCE_AUTOPILOT_EXECUTION_STATUS_PATTERN = "^(executed|reversed)$"
GOVERNANCE_AUTOPILOT_RUNNER_SIMULATION_STATUS_PATTERN = (
    "^(ready_for_runner|not_ready|blocked|approval_required|policy_denied|capability_denied|archived)$"
)
GOVERNANCE_AUTOPILOT_RUNNER_ADMISSION_STATUS_PATTERN = "^(admitted|blocked|revoked|expired|archived)$"
GOVERNANCE_AUTOPILOT_RUNNER_SESSION_STATUS_PATTERN = "^(active|expired|locked|revoked|archived)$"
GOVERNANCE_AUTOPILOT_RUNNER_HANDSHAKE_STATUS_PATTERN = (
    "^(ready_for_future_runner|blocked|session_expired|session_locked|session_revoked|admission_revoked|revoked|archived)$"
)
GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_PATTERN = "^(logged|blocked|archived)$"
GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_TYPE_PATTERN = "^(noop_runner_control_plane_check)$"


class AISystemRiskAssessmentCreate(BaseModel):
    ai_system_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    assessment_type: str = Field(pattern=AI_RISK_ASSESSMENT_TYPE_PATTERN)
    status: str = Field(default="draft", pattern=AI_RISK_ASSESSMENT_STATUS_PATTERN)
    owner_user_id: UUID | None = None
    risk_level: str = Field(default="unknown", pattern=AI_RISK_VALUE_PATTERN)
    likelihood: str = Field(default="unknown", pattern=AI_RISK_VALUE_PATTERN)
    impact: str = Field(default="unknown", pattern=AI_RISK_VALUE_PATTERN)
    risk_dimensions_json: dict | list | None = None
    risk_factors_json: dict | list | None = None
    mitigation_summary: str | None = None
    assumptions: str | None = None
    limitations: str | None = None
    methodology_version: str = Field(default="v1", min_length=1, max_length=64)


class AISystemRiskAssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    assessment_type: str | None = Field(default=None, pattern=AI_RISK_ASSESSMENT_TYPE_PATTERN)
    owner_user_id: UUID | None = None
    risk_level: str | None = Field(default=None, pattern=AI_RISK_VALUE_PATTERN)
    likelihood: str | None = Field(default=None, pattern=AI_RISK_VALUE_PATTERN)
    impact: str | None = Field(default=None, pattern=AI_RISK_VALUE_PATTERN)
    risk_dimensions_json: dict | list | None = None
    risk_factors_json: dict | list | None = None
    mitigation_summary: str | None = None
    assumptions: str | None = None
    limitations: str | None = None
    methodology_version: str | None = Field(default=None, min_length=1, max_length=64)


class AISystemRiskAssessmentArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemRiskAssessmentManualSnapshotRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AISystemRiskAssessmentRead(UUIDTimestampSchema):
    organization_id: UUID
    ai_system_id: UUID
    title: str
    description: str | None = None
    assessment_type: str
    status: str
    owner_user_id: UUID | None = None
    risk_level: str
    likelihood: str
    impact: str
    scoring_profile_id: UUID | None = None
    scoring_profile_snapshot_json: dict | list | None = None
    score_explanation_json: dict | list | None = None
    calculated_risk_level: str | None = None
    dimension_template_id: UUID | None = None
    latest_classification_id: UUID | None = None
    classification_status: str | None = None
    classification_summary_json: dict | list | None = None
    latest_classification_review_status: str | None = None
    open_signal_count: int | None = None
    dimension_template_snapshot_json: dict | list | None = None
    dimension_inputs_json: dict | list | None = None
    dimension_score_json: dict | list | None = None
    dimension_weighted_score: float | None = None
    calculated_dimension_risk_level: str | None = None
    residual_likelihood: str | None = None
    residual_impact: str | None = None
    calculated_residual_risk_level: str | None = None
    residual_score_explanation_json: dict | list | None = None
    inherent_risk_score: int | None = None
    residual_risk_score: int | None = None
    risk_dimensions_json: dict | list | None = None
    risk_factors_json: dict | list | None = None
    mitigation_summary: str | None = None
    assumptions: str | None = None
    limitations: str | None = None
    methodology_version: str
    completed_at: datetime | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    caveat: str


class AISystemRiskAssessmentSnapshotRead(UUIDTimestampSchema):
    organization_id: UUID
    risk_assessment_id: UUID
    ai_system_id: UUID
    snapshot_type: str
    snapshot_version: int
    snapshot_json: dict | list
    snapshot_sha256: str
    created_by_user_id: UUID | None = None
    caveat: str


class AISystemRiskAssessmentSummary(BaseModel):
    total_assessments: int
    draft_assessments: int
    in_review_assessments: int
    completed_assessments: int
    archived_assessments: int
    by_risk_level: dict[str, int]
    by_assessment_type: dict[str, int]
    by_ai_system: dict[str, int]
    by_calculated_dimension_risk_level: dict[str, int]
    by_calculated_residual_risk_level: dict[str, int]
    total_snapshots: int
    latest_completed_at: datetime | None = None
    caveat: str


class AISystemRiskScoringProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    likelihood_weights_json: dict | None = None
    impact_weights_json: dict | None = None
    risk_level_thresholds_json: list | None = None
    methodology_version: str = Field(default="manual-configurable-v1", min_length=1, max_length=64)
    is_default: bool = False
    status: str = Field(default="active", pattern=AI_RISK_SCORING_PROFILE_STATUS_PATTERN)


class AISystemRiskScoringProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    likelihood_weights_json: dict | None = None
    impact_weights_json: dict | None = None
    risk_level_thresholds_json: list | None = None
    methodology_version: str | None = Field(default=None, min_length=1, max_length=64)
    is_default: bool | None = None
    status: str | None = Field(default=None, pattern=AI_RISK_SCORING_PROFILE_STATUS_PATTERN)


class AISystemRiskScoringProfileArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemRiskScorePreviewRequest(BaseModel):
    likelihood: str = Field(pattern=AI_RISK_VALUE_PATTERN)
    impact: str = Field(pattern=AI_RISK_VALUE_PATTERN)


class AISystemRiskScorePreviewResponse(BaseModel):
    inherent_risk_score: int | None = None
    calculated_risk_level: str | None = None
    score_explanation: dict
    caveat: str


class AISystemRiskAssessmentRecalculateRequest(BaseModel):
    scoring_profile_id: UUID | None = None
    apply_calculated_risk_level_to_manual_risk_level: bool = False


class AISystemRiskDimensionTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    dimension_weights_json: dict
    dimension_thresholds_json: list
    methodology_version: str = Field(default="manual-dimension-v1", min_length=1, max_length=64)
    is_default: bool = False
    status: str = Field(default="active", pattern=AI_RISK_DIMENSION_TEMPLATE_STATUS_PATTERN)


class AISystemRiskDimensionTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    dimension_weights_json: dict | None = None
    dimension_thresholds_json: list | None = None
    methodology_version: str | None = Field(default=None, min_length=1, max_length=64)
    is_default: bool | None = None
    status: str | None = Field(default=None, pattern=AI_RISK_DIMENSION_TEMPLATE_STATUS_PATTERN)


class AISystemRiskDimensionTemplateArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemRiskDimensionTemplateRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    is_default: bool
    dimension_weights_json: dict
    dimension_thresholds_json: list
    methodology_version: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemRiskDimensionScorePreviewRequest(BaseModel):
    dimension_inputs_json: dict


class AISystemRiskDimensionScorePreviewResponse(BaseModel):
    dimension_weighted_score: float | None = None
    calculated_dimension_risk_level: str | None = None
    dimension_score_json: dict
    caveat: str


class AISystemRiskAssessmentApplyDimensionTemplateRequest(BaseModel):
    dimension_template_id: UUID | None = None
    dimension_inputs_json: dict


class AISystemRiskAssessmentResidualRiskPreviewRequest(BaseModel):
    residual_likelihood: str = Field(pattern=AI_RISK_VALUE_PATTERN)
    residual_impact: str = Field(pattern=AI_RISK_VALUE_PATTERN)
    scoring_profile_id: UUID | None = None


class AISystemRiskAssessmentResidualRiskPreviewResponse(BaseModel):
    residual_risk_score: int | None = None
    calculated_residual_risk_level: str | None = None
    residual_score_explanation: dict
    caveat: str


class AISystemRiskAssessmentApplyResidualRiskRequest(BaseModel):
    residual_likelihood: str = Field(pattern=AI_RISK_VALUE_PATTERN)
    residual_impact: str = Field(pattern=AI_RISK_VALUE_PATTERN)
    scoring_profile_id: UUID | None = None


class AISystemRiskScoringProfileRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    is_default: bool
    likelihood_weights_json: dict
    impact_weights_json: dict
    risk_level_thresholds_json: list
    methodology_version: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemRiskScoringProfileSummary(BaseModel):
    total_profiles: int
    active_profiles: int
    inactive_profiles: int
    archived_profiles: int
    default_profile_id: UUID | None = None
    assessments_with_scoring_profile: int
    assessments_without_scoring_profile: int
    by_calculated_risk_level: dict[str, int]
    caveat: str


class AISystemRiskDimensionTemplateSummary(BaseModel):
    total_templates: int
    active_templates: int
    inactive_templates: int
    archived_templates: int
    default_template_id: UUID | None = None
    assessments_with_dimension_template: int
    assessments_without_dimension_template: int
    by_calculated_dimension_risk_level: dict[str, int]
    by_calculated_residual_risk_level: dict[str, int]
    caveat: str


class AISystemRiskClassificationTaxonomyTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    taxonomy_json: dict
    methodology_version: str = Field(default="manual-classification-v1", min_length=1, max_length=64)
    is_default: bool = False
    status: str = Field(default="active", pattern=AI_RISK_CLASSIFICATION_TAXONOMY_STATUS_PATTERN)


class AISystemRiskClassificationTaxonomyTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    taxonomy_json: dict | None = None
    methodology_version: str | None = Field(default=None, min_length=1, max_length=64)
    is_default: bool | None = None
    status: str | None = Field(default=None, pattern=AI_RISK_CLASSIFICATION_TAXONOMY_STATUS_PATTERN)


class AISystemRiskClassificationTaxonomyTemplateArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemRiskClassificationTaxonomyTemplateRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    is_default: bool
    taxonomy_json: dict
    methodology_version: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemRiskClassificationRecordCreate(BaseModel):
    taxonomy_template_id: UUID | None = None
    classification_json: dict
    confidence_level: str = Field(default="unknown", pattern=AI_RISK_CLASSIFICATION_CONFIDENCE_PATTERN)
    justification: str = Field(min_length=1)
    source_type: str | None = Field(default=None, pattern=AI_RISK_CLASSIFICATION_SOURCE_TYPE_PATTERN)
    source_reference: str | None = None
    evidence_ids_json: list[str] | None = None
    control_ids_json: list[str] | None = None
    risk_ids_json: list[str] | None = None
    supersede_previous: bool = True


class AISystemRiskClassificationRecordRead(UUIDTimestampSchema):
    organization_id: UUID
    ai_system_id: UUID
    risk_assessment_id: UUID
    taxonomy_template_id: UUID | None = None
    taxonomy_template_snapshot_json: dict | list | None = None
    classification_json: dict
    status: str
    review_status: str
    review_requested_at: datetime | None = None
    review_requested_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    reviewed_by_user_id: UUID | None = None
    review_note: str | None = None
    change_request_note: str | None = None
    rejected_at: datetime | None = None
    rejected_by_user_id: UUID | None = None
    rejection_reason: str | None = None
    latest_snapshot_id: UUID | None = None
    open_signal_count: int | None = None
    confidence_level: str
    justification: str
    source_type: str | None = None
    source_reference: str | None = None
    evidence_ids_json: list[str] | None = None
    control_ids_json: list[str] | None = None
    risk_ids_json: list[str] | None = None
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    caveat: str


class AISystemRiskClassificationRecordArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemRiskClassificationSubmitForReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AISystemRiskClassificationRequestChangesRequest(BaseModel):
    change_request_note: str = Field(min_length=1, max_length=5000)


class AISystemRiskClassificationMarkReviewedRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=5000)


class AISystemRiskClassificationRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=5000)


class AISystemRiskClassificationSnapshotCreate(BaseModel):
    snapshot_type: str = Field(default="manual_snapshot", pattern=AI_RISK_CLASSIFICATION_SNAPSHOT_TYPE_PATTERN)


class AISystemRiskClassificationSnapshotRead(UUIDTimestampSchema):
    organization_id: UUID
    classification_id: UUID
    risk_assessment_id: UUID
    ai_system_id: UUID
    snapshot_type: str
    snapshot_version: int
    snapshot_json: dict | list
    snapshot_sha256: str
    created_by_user_id: UUID | None = None
    caveat: str


class GovernanceSignalRead(UUIDTimestampSchema):
    organization_id: UUID
    domain: str
    entity_type: str
    entity_id: UUID
    related_ai_system_id: UUID | None = None
    related_risk_assessment_id: UUID | None = None
    signal_type: str
    reason_code: str
    severity: str
    status: str
    title: str
    message: str
    source_json: dict | list
    created_by_system: bool
    resolved_at: datetime | None = None
    resolved_by_user_id: UUID | None = None
    resolve_reason: str | None = None
    dismissed_at: datetime | None = None
    dismissed_by_user_id: UUID | None = None
    dismiss_reason: str | None = None
    priority_score: float | None = None
    priority_band: str | None = Field(default=None, pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    priority_explanation_json: dict | list | None = None
    group_key: str | None = None
    age_days: int | None = None
    status_age_days: int | None = None
    assessment_age_days: int | None = None
    stale_signal: bool = False
    stale_assessment_context: bool = False
    context_flags: list[str] = Field(default_factory=list)
    caveat: str


class GovernanceSignalActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class GovernanceSignalSummary(BaseModel):
    total_signals: int
    open_signals: int
    resolved_signals: int
    dismissed_signals: int
    by_severity: dict[str, int]
    by_signal_type: dict[str, int]
    by_entity_type: dict[str, int]
    latest_signal_at: datetime | None = None
    stale_open_signals: int = 0
    oldest_open_signal_age_days: int | None = None
    open_critical_signals: int = 0
    open_high_or_urgent_priority_signals: int = 0
    open_signals_with_stale_assessment_context: int = 0
    context_flags: list[str] = Field(default_factory=list)
    caveat: str


class GovernanceSignalPrioritizedRead(BaseModel):
    signal_id: UUID
    signal_type: str
    reason_code: str
    severity: str
    status: str
    entity_type: str
    entity_id: UUID
    related_ai_system_id: UUID | None = None
    related_risk_assessment_id: UUID | None = None
    priority_score: float
    priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    priority_explanation_json: dict
    age_days: int
    status_age_days: int | None = None
    assessment_age_days: int | None = None
    stale_assessment_context: bool = False
    group_key: str
    context_flags: list[str] = Field(default_factory=list)
    created_at: datetime
    caveat: str


class GovernanceSignalGroupRead(BaseModel):
    group_key: str
    group_title: str
    related_ai_system_id: UUID | None = None
    related_risk_assessment_id: UUID | None = None
    signal_count: int
    highest_priority_score: float
    highest_priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    severities_count: dict[str, int]
    reason_codes_count: dict[str, int]
    signals: list[GovernanceSignalPrioritizedRead]
    caveat: str


class GovernanceSignalAttentionRead(BaseModel):
    ai_system_id: UUID
    open_signal_count: int
    highest_priority_score: float
    highest_priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    top_signals: list[GovernanceSignalPrioritizedRead]
    latest_risk_assessment_id: UUID | None = None
    latest_manual_risk_level: str | None = None
    latest_calculated_residual_risk_level: str | None = None
    attention_summary: dict
    caveat: str


class GovernanceSignalPrioritySummary(BaseModel):
    total_open_signals: int
    by_priority_band: dict[str, int]
    by_severity: dict[str, int]
    urgent_signal_count: int
    high_signal_count: int
    top_ai_systems_by_attention: list[dict]
    oldest_open_signal_at: datetime | None = None
    caveat: str


class GovernanceSignalPriorityExplanation(BaseModel):
    signal_id: UUID
    base_severity_weight: int
    age_weight: int
    entity_risk_context_weight: int
    signal_density_weight: int
    total_priority_score: float
    priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    source_fields: dict
    caveat: str


class GovernanceActionTemplateRead(BaseModel):
    action_key: str
    title: str
    description: str
    action_type: str = Field(pattern=GOVERNANCE_CANDIDATE_ACTION_TYPE_PATTERN)
    source_reason_codes: list[str]
    default_priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    recommended_owner_type: str
    target_entity_type: str
    target_route_hint: str | None = None
    human_approval_required: bool
    automation_allowed: bool
    caveat: str


class GovernanceActionTemplateCatalogResponse(BaseModel):
    templates: list[GovernanceActionTemplateRead]
    count: int
    caveat: str


class GovernanceCandidateActionRead(BaseModel):
    action_key: str
    title: str
    description: str
    action_type: str = Field(pattern=GOVERNANCE_CANDIDATE_ACTION_TYPE_PATTERN)
    priority_score: float
    priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    source_signal_ids: list[UUID]
    source_reason_codes: list[str]
    target_entity_type: str
    target_entity_id: UUID | None = None
    related_ai_system_id: UUID | None = None
    related_risk_assessment_id: UUID | None = None
    rationale: str
    rationale_json: dict
    human_approval_required: bool
    automation_allowed: bool
    risk_tier: str = Field(default="medium", pattern=GOVERNANCE_AUTOPILOT_ACTION_RISK_TIER_PATTERN)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    target_route_hint: str | None = None
    caveat: str


class GovernanceAISystemCandidateActionsRead(BaseModel):
    ai_system_id: UUID
    candidate_action_count: int
    highest_priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    actions: list[GovernanceCandidateActionRead]
    caveat: str


class GovernanceRiskAssessmentCandidateActionsRead(BaseModel):
    assessment_id: UUID
    candidate_action_count: int
    highest_priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    actions: list[GovernanceCandidateActionRead]
    caveat: str


class GovernanceCandidateActionSummary(BaseModel):
    total_candidate_actions: int
    by_action_type: dict[str, int]
    by_priority_band: dict[str, int]
    top_action_keys: list[dict]
    top_ai_systems_by_action_count: list[dict]
    caveat: str


class GovernanceRecommendationSnapshotFilter(BaseModel):
    priority_band: str | None = Field(default=None, pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    action_type: str | None = Field(default=None, pattern=GOVERNANCE_CANDIDATE_ACTION_TYPE_PATTERN)
    reason_code: str | None = None


class GovernanceRecommendationSnapshotPreviewRequest(BaseModel):
    scope_type: str = Field(pattern=GOVERNANCE_RECOMMENDATION_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    filters: GovernanceRecommendationSnapshotFilter | None = None


class GovernanceRecommendationSnapshotCreateRequest(BaseModel):
    scope_type: str = Field(pattern=GOVERNANCE_RECOMMENDATION_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    filters: GovernanceRecommendationSnapshotFilter | None = None


class GovernanceRecommendationSnapshotPreviewResponse(BaseModel):
    scope_type: str = Field(pattern=GOVERNANCE_RECOMMENDATION_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    candidate_count: int
    recommendation_payload_json: dict
    source_signal_ids: list[UUID]
    source_candidate_hash: str
    caveat: str


class GovernanceRecommendationSnapshotRead(UUIDTimestampSchema):
    snapshot_id: UUID
    organization_id: UUID
    scope_type: str = Field(pattern=GOVERNANCE_RECOMMENDATION_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    source_type: str = Field(pattern=GOVERNANCE_RECOMMENDATION_SOURCE_TYPE_PATTERN)
    candidate_count: int
    recommendation_payload_json: dict | list
    source_signal_ids_json: list
    source_candidate_hash: str
    snapshot_sha256: str
    snapshot_version: int
    previous_snapshot_id: UUID | None = None
    diff_from_previous_json: dict | list | None = None
    created_by_user_id: UUID | None = None
    actions_overlay: list[dict] | None = None
    caveat: str


class GovernanceRecommendationSnapshotDiffResponse(BaseModel):
    base_snapshot_id: UUID
    compare_snapshot_id: UUID
    added_actions: list[dict]
    removed_actions: list[dict]
    changed_actions: list[dict]
    unchanged_action_count: int
    caveat: str


class GovernanceRecommendationSnapshotSummary(BaseModel):
    total_snapshots: int
    by_scope_type: dict[str, int]
    latest_snapshot_at: datetime | None = None
    scopes_with_snapshots: int
    caveat: str


class GovernanceRecommendationSnapshotActionRead(BaseModel):
    action_identity_hash: str
    action_key: str
    title: str
    description: str
    action_type: str = Field(pattern=GOVERNANCE_CANDIDATE_ACTION_TYPE_PATTERN)
    priority_score: float
    priority_band: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    source_signal_ids: list[UUID]
    source_reason_codes: list[str]
    target_entity_type: str
    target_entity_id: UUID | None = None
    related_ai_system_id: UUID | None = None
    related_risk_assessment_id: UUID | None = None
    rationale: str
    rationale_json: dict
    human_approval_required: bool
    automation_allowed: bool
    risk_tier: str = Field(default="medium", pattern=GOVERNANCE_AUTOPILOT_ACTION_RISK_TIER_PATTERN)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    target_route_hint: str | None = None
    disposition: dict | None = None
    caveat: str


class GovernanceRecommendationSnapshotActionsResponse(BaseModel):
    snapshot_id: UUID
    action_count: int
    actions: list[GovernanceRecommendationSnapshotActionRead]
    caveat: str


class GovernanceRecommendationActionAcknowledgeRequest(BaseModel):
    note: str | None = None


class GovernanceRecommendationActionDismissRequest(BaseModel):
    reason: str = Field(min_length=1)
    note: str | None = None


class GovernanceRecommendationActionDeferRequest(BaseModel):
    reason: str = Field(min_length=1)
    deferred_until: datetime | None = None
    note: str | None = None


class GovernanceRecommendationActionAcceptRequest(BaseModel):
    note: str | None = None


class GovernanceRecommendationActionDispositionRead(UUIDTimestampSchema):
    disposition_id: UUID
    recommendation_snapshot_id: UUID
    action_identity_hash: str
    action_key: str
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None
    related_ai_system_id: UUID | None = None
    related_risk_assessment_id: UUID | None = None
    disposition_status: str = Field(pattern=GOVERNANCE_RECOMMENDATION_DISPOSITION_STATUS_PATTERN)
    note: str | None = None
    reason: str | None = None
    deferred_until: datetime | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    caveat: str


class GovernanceRecommendationActionDispositionSummary(BaseModel):
    total_dispositions: int
    by_status: dict[str, int]
    by_action_key: dict[str, int]
    by_ai_system: list[dict]
    latest_disposition_at: datetime | None = None
    caveat: str


class GovernanceCopilotDraftTypeRead(BaseModel):
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    title: str
    description: str
    scope_types: list[str]


class GovernanceCopilotDraftTypeCatalogResponse(BaseModel):
    draft_types: list[GovernanceCopilotDraftTypeRead]
    count: int
    caveat: str


class GovernanceCopilotDraftPreviewRequest(BaseModel):
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    scope_type: str = Field(pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    include_resolved_signals: bool = False
    include_dismissed_recommendations: bool = False


class GovernanceCopilotDraftPreviewRead(BaseModel):
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    title: str
    executive_summary: str
    key_findings: list[str]
    recommended_next_steps: list[str]
    open_questions: list[str]
    source_signal_ids: list[UUID]
    source_recommendation_snapshot_id: UUID | None = None
    source_action_identity_hashes: list[str]
    source_entities_json: dict
    generated_at: datetime
    generation_mode: str = Field(pattern=GOVERNANCE_COPILOT_GENERATION_MODE_PATTERN)
    caveat: str


class GovernanceCopilotDraftSnapshotPreviewRequest(BaseModel):
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    scope_type: str = Field(pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    include_resolved_signals: bool = False
    include_dismissed_recommendations: bool = False


class GovernanceCopilotDraftSnapshotCreateRequest(BaseModel):
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    scope_type: str = Field(pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    include_resolved_signals: bool = False
    include_dismissed_recommendations: bool = False


class GovernanceCopilotDraftSnapshotPreviewResponse(BaseModel):
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    scope_type: str = Field(pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    draft_payload_json: dict
    source_entities_json: dict
    source_signal_ids: list[UUID]
    source_recommendation_snapshot_id: UUID | None = None
    source_action_identity_hashes: list[str]
    source_context_hash: str
    caveat: str


class GovernanceCopilotDraftSnapshotRead(UUIDTimestampSchema):
    snapshot_id: UUID
    organization_id: UUID
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    scope_type: str = Field(pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN)
    scope_id: UUID | None = None
    draft_payload_json: dict | list
    source_entities_json: dict | list
    source_signal_ids_json: list
    source_recommendation_snapshot_id: UUID | None = None
    source_action_identity_hashes_json: list
    source_context_hash: str
    snapshot_sha256: str
    snapshot_version: int
    previous_snapshot_id: UUID | None = None
    diff_from_previous_json: dict | list | None = None
    created_by_user_id: UUID | None = None
    caveat: str


class GovernanceCopilotDraftSnapshotDiffResponse(BaseModel):
    base_snapshot_id: UUID
    compare_snapshot_id: UUID
    executive_summary_changed: bool
    added_key_findings: list[str]
    removed_key_findings: list[str]
    added_next_steps: list[str]
    removed_next_steps: list[str]
    added_open_questions: list[str]
    removed_open_questions: list[str]
    source_reference_changes: dict
    caveat: str


class GovernanceCopilotDraftSnapshotSummary(BaseModel):
    total_snapshots: int
    by_draft_type: dict[str, int]
    by_scope_type: dict[str, int]
    latest_snapshot_at: datetime | None = None
    scopes_with_snapshots: int
    caveat: str


class GovernanceAutopilotPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="active", pattern=GOVERNANCE_AUTOPILOT_POLICY_STATUS_PATTERN)
    is_default: bool = False
    mode: str = Field(default="suggest_only", pattern=GOVERNANCE_AUTOPILOT_POLICY_MODE_PATTERN)
    allowed_action_types_json: list[str] | None = None
    blocked_action_types_json: list[str] | None = None
    allowed_draft_types_json: list[str] | None = None
    blocked_draft_types_json: list[str] | None = None
    allowed_signal_reason_codes_json: list[str] | None = None
    blocked_signal_reason_codes_json: list[str] | None = None
    approval_required_action_types_json: list[str] | None = None
    approval_required_priority_bands_json: list[str] | None = None
    max_allowed_priority_band_for_auto: str = Field(default="low", pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    external_effects_allowed: bool = False
    task_creation_allowed: bool = False
    review_creation_allowed: bool = False
    source_record_mutation_allowed: bool = False
    policy_json: dict | list | None = None


class GovernanceAutopilotPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=GOVERNANCE_AUTOPILOT_POLICY_STATUS_PATTERN)
    is_default: bool | None = None
    mode: str | None = Field(default=None, pattern=GOVERNANCE_AUTOPILOT_POLICY_MODE_PATTERN)
    allowed_action_types_json: list[str] | None = None
    blocked_action_types_json: list[str] | None = None
    allowed_draft_types_json: list[str] | None = None
    blocked_draft_types_json: list[str] | None = None
    allowed_signal_reason_codes_json: list[str] | None = None
    blocked_signal_reason_codes_json: list[str] | None = None
    approval_required_action_types_json: list[str] | None = None
    approval_required_priority_bands_json: list[str] | None = None
    max_allowed_priority_band_for_auto: str | None = Field(default=None, pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    external_effects_allowed: bool | None = None
    task_creation_allowed: bool | None = None
    review_creation_allowed: bool | None = None
    source_record_mutation_allowed: bool | None = None
    policy_json: dict | list | None = None


class GovernanceAutopilotPolicyArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotPolicyRead(BaseModel):
    id: UUID | None = None
    policy_id: UUID | None = None
    organization_id: UUID | None = None
    name: str
    description: str | None = None
    status: str = Field(pattern=GOVERNANCE_AUTOPILOT_POLICY_STATUS_PATTERN)
    is_default: bool
    mode: str = Field(pattern=GOVERNANCE_AUTOPILOT_POLICY_MODE_PATTERN)
    allowed_action_types_json: list[str]
    blocked_action_types_json: list[str]
    allowed_draft_types_json: list[str]
    blocked_draft_types_json: list[str]
    allowed_signal_reason_codes_json: list[str]
    blocked_signal_reason_codes_json: list[str]
    approval_required_action_types_json: list[str]
    approval_required_priority_bands_json: list[str]
    max_allowed_priority_band_for_auto: str = Field(pattern=GOVERNANCE_SIGNAL_PRIORITY_BAND_PATTERN)
    external_effects_allowed: bool
    task_creation_allowed: bool
    review_creation_allowed: bool
    source_record_mutation_allowed: bool
    policy_json: dict
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_source: str | None = None
    caveat: str


class GovernanceAutopilotApprovalPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="active", pattern=GOVERNANCE_AUTOPILOT_APPROVAL_POLICY_STATUS_PATTERN)
    is_default: bool = False
    minimum_approvals: int = Field(default=1, ge=1)
    rejection_threshold: int = Field(default=1, ge=1)
    require_distinct_approvers: bool = True
    block_requester_self_approval: bool = True
    require_quorum_for_priority_bands_json: list[str] | None = None
    require_quorum_for_source_types_json: list[str] | None = None
    policy_json: dict | list | None = None


class GovernanceAutopilotApprovalPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=GOVERNANCE_AUTOPILOT_APPROVAL_POLICY_STATUS_PATTERN)
    is_default: bool | None = None
    minimum_approvals: int | None = Field(default=None, ge=1)
    rejection_threshold: int | None = Field(default=None, ge=1)
    require_distinct_approvers: bool | None = None
    block_requester_self_approval: bool | None = None
    require_quorum_for_priority_bands_json: list[str] | None = None
    require_quorum_for_source_types_json: list[str] | None = None
    policy_json: dict | list | None = None


class GovernanceAutopilotApprovalPolicyArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotApprovalPolicyRead(BaseModel):
    approval_policy_id: UUID | None = None
    organization_id: UUID | None = None
    name: str
    description: str | None = None
    status: str = Field(pattern=GOVERNANCE_AUTOPILOT_APPROVAL_POLICY_STATUS_PATTERN)
    is_default: bool
    minimum_approvals: int
    rejection_threshold: int
    require_distinct_approvers: bool
    block_requester_self_approval: bool
    require_quorum_for_priority_bands_json: list[str]
    require_quorum_for_source_types_json: list[str]
    policy_json: dict
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_source: str | None = None
    caveat: str


class GovernanceAutopilotApprovalPolicySummary(BaseModel):
    total_policies: int
    active_policies: int
    archived_policies: int
    default_policy_id: UUID | None = None
    resolved_minimum_approvals: int
    resolved_rejection_threshold: int
    block_requester_self_approval: bool
    caveat: str


class GovernanceAutopilotEvaluateCandidateActionRequest(BaseModel):
    candidate_action_json: dict
    policy_id: UUID | None = None


class GovernanceAutopilotEvaluateCandidateActionResponse(BaseModel):
    allowed_by_policy: bool
    required_mode: str = Field(pattern=GOVERNANCE_AUTOPILOT_POLICY_MODE_PATTERN)
    requires_human_approval: bool
    risk_tier: str = Field(pattern=GOVERNANCE_AUTOPILOT_ACTION_RISK_TIER_PATTERN)
    confidence_score: float = Field(ge=0.0, le=1.0)
    blocked_reasons: list[str]
    policy_decision: str
    policy_explanation_json: dict
    policy_data_age_days: int | None = None
    context_flags: list[str] = Field(default_factory=list)
    execution_mode: str = "planning_only"
    caveat: str


class GovernanceAutopilotEvaluateRecommendationSnapshotRequest(BaseModel):
    recommendation_snapshot_id: UUID
    policy_id: UUID | None = None


class GovernanceAutopilotEvaluateRecommendationSnapshotResponse(BaseModel):
    snapshot_id: UUID
    total_actions: int
    allowed_count: int
    blocked_count: int
    approval_required_count: int
    blocked_ratio: float = 0
    highest_risk_tier: str = Field(pattern=GOVERNANCE_AUTOPILOT_ACTION_RISK_TIER_PATTERN)
    decisions: list[dict]
    context_flags: list[str] = Field(default_factory=list)
    caveat: str


class GovernanceAutopilotEvaluateCopilotDraftSnapshotRequest(BaseModel):
    copilot_draft_snapshot_id: UUID
    policy_id: UUID | None = None


class GovernanceAutopilotEvaluateCopilotDraftSnapshotResponse(BaseModel):
    snapshot_id: UUID
    draft_type: str = Field(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN)
    allowed_by_policy: bool
    requires_human_approval: bool
    blocked_reasons: list[str]
    policy_explanation_json: dict
    policy_data_age_days: int | None = None
    context_flags: list[str] = Field(default_factory=list)
    caveat: str


class GovernanceAutopilotSummary(BaseModel):
    total_policies: int
    active_policies: int
    archived_policies: int
    default_policy_id: UUID | None = None
    resolved_mode: str = Field(pattern=GOVERNANCE_AUTOPILOT_POLICY_MODE_PATTERN)
    resolved_source: str | None = None
    external_effects_allowed: bool
    task_creation_allowed: bool
    review_creation_allowed: bool
    source_record_mutation_allowed: bool
    pending_execution_intents: int = 0
    pending_approval_requests: int = 0
    open_critical_signals: int = 0
    policy_data_age_days: int | None = None
    stale_default_policy: bool = False
    context_flags: list[str] = Field(default_factory=list)
    caveat: str


class GovernanceAutopilotCapabilitiesResponse(BaseModel):
    capabilities: list[dict]
    caveat: str


class GovernanceAutopilotExecutionIntentPreviewCandidateActionRequest(BaseModel):
    candidate_action_json: dict
    policy_id: UUID | None = None


class GovernanceAutopilotExecutionIntentPreviewRecommendationSnapshotRequest(BaseModel):
    recommendation_snapshot_id: UUID
    policy_id: UUID | None = None


class GovernanceAutopilotExecutionIntentPreviewCopilotDraftSnapshotRequest(BaseModel):
    copilot_draft_snapshot_id: UUID
    policy_id: UUID | None = None


class GovernanceAutopilotExecutionIntentPreviewResponse(BaseModel):
    source_type: str = Field(pattern=GOVERNANCE_AUTOPILOT_INTENT_SOURCE_TYPE_PATTERN)
    source_id: UUID | None = None
    plan_payload_json: dict
    capability_decisions_json: dict | list
    approval_required: bool
    blocked: bool
    blocked_reasons: list[str]
    source_entities_json: dict
    source_hash: str
    caveat: str


class GovernanceAutopilotExecutionIntentCreate(BaseModel):
    source_type: str = Field(pattern=GOVERNANCE_AUTOPILOT_INTENT_SOURCE_TYPE_PATTERN)
    source_id: UUID | None = None
    candidate_action_json: dict | None = None
    policy_id: UUID | None = None


class GovernanceAutopilotExecutionIntentRead(UUIDTimestampSchema):
    intent_id: UUID
    organization_id: UUID
    source_type: str = Field(pattern=GOVERNANCE_AUTOPILOT_INTENT_SOURCE_TYPE_PATTERN)
    source_id: UUID | None = None
    policy_id: UUID | None = None
    intent_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_INTENT_STATUS_PATTERN)
    plan_payload_json: dict | list
    capability_decisions_json: dict | list
    approval_required: bool
    blocked: bool
    blocked_reasons_json: list | None = None
    source_entities_json: dict | list
    source_hash: str
    intent_sha256: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archive_reason: str | None = None
    intent_age_hours: float | None = None
    stale_intent: bool = False
    context_flags: list[str] = Field(default_factory=list)
    execution_mode: str = "planning_only"
    caveat: str


class GovernanceAutopilotExecutionIntentArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotExecutionIntentSummary(BaseModel):
    total_intents: int
    by_status: dict[str, int]
    by_source_type: dict[str, int]
    blocked_count: int
    approval_required_count: int
    pending_intents: int = 0
    stale_pending_intents: int = 0
    oldest_pending_intent_at: datetime | None = None
    latest_intent_at: datetime | None = None
    latest_intent_age_hours: float | None = None
    context_flags: list[str] = Field(default_factory=list)
    caveat: str


class GovernanceAutopilotExecutionApprovalRequestCreate(BaseModel):
    approval_note: str | None = None


class GovernanceAutopilotExecutionApprovalApproveRequest(BaseModel):
    decision_reason: str | None = None
    approval_note: str | None = None


class GovernanceAutopilotExecutionApprovalRejectRequest(BaseModel):
    decision_reason: str = Field(min_length=1, max_length=2000)


class GovernanceAutopilotExecutionApprovalCancelRequest(BaseModel):
    decision_reason: str | None = None


class GovernanceAutopilotExecutionReverseRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotExecutionRead(UUIDTimestampSchema):
    execution_id: UUID
    organization_id: UUID
    execution_intent_id: UUID
    action_key: str
    action_type: str
    risk_tier: str = Field(pattern=GOVERNANCE_AUTOPILOT_ACTION_RISK_TIER_PATTERN)
    confidence_score: float = Field(ge=0.0, le=1.0)
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None
    execution_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_EXECUTION_STATUS_PATTERN)
    before_snapshot_json: dict | list
    after_snapshot_json: dict | list
    reversal_deadline_at: datetime
    reversed_at: datetime | None = None
    reversed_by_user_id: UUID | None = None
    reversal_reason: str | None = None
    reversal_snapshot_json: dict | list | None = None
    metadata_json: dict | list | None = None


class GovernanceAutopilotExecutionApprovalRead(UUIDTimestampSchema):
    approval_id: UUID
    organization_id: UUID
    execution_intent_id: UUID
    approval_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_APPROVAL_STATUS_PATTERN)
    requested_by_user_id: UUID | None = None
    requested_at: datetime
    decided_by_user_id: UUID | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    approval_note: str | None = None
    approval_policy_snapshot_json: dict | list
    approval_requirements_json: dict | list
    readiness_snapshot_json: dict | list
    cancelled_at: datetime | None = None
    approval_vote_count: int = 0
    rejection_vote_count: int = 0
    quorum_met: bool = False
    rejection_threshold_met: bool = False
    readiness_state: str = Field(pattern=GOVERNANCE_AUTOPILOT_READINESS_STATE_PATTERN)
    ready_for_runner: bool
    caveat: str


class GovernanceAutopilotExecutionApprovalVoteApproveRequest(BaseModel):
    vote_reason: str | None = None
    vote_note: str | None = None


class GovernanceAutopilotExecutionApprovalVoteRejectRequest(BaseModel):
    vote_reason: str = Field(min_length=1, max_length=2000)
    vote_note: str | None = None


class GovernanceAutopilotExecutionApprovalVoteRead(UUIDTimestampSchema):
    vote_id: UUID
    approval_id: UUID
    execution_intent_id: UUID
    organization_id: UUID
    vote_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_VOTE_STATUS_PATTERN)
    voter_user_id: UUID | None = None
    vote_reason: str | None = None
    vote_note: str | None = None
    caveat: str


class GovernanceAutopilotExecutionApprovalQuorumStatusResponse(BaseModel):
    approval_id: UUID
    execution_intent_id: UUID
    approval_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_APPROVAL_STATUS_PATTERN)
    minimum_approvals: int
    approval_vote_count: int
    rejection_vote_count: int
    rejection_threshold: int
    quorum_met: bool
    rejection_threshold_met: bool
    ready_for_runner: bool
    blocked_reasons: list[str]
    resolved_approval_policy: dict
    caveat: str


class GovernanceAutopilotExecutionIntentApprovalRequirementsResponse(BaseModel):
    intent_id: UUID
    intent_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_INTENT_STATUS_PATTERN)
    approval_required: bool
    blocked: bool
    approval_requirement_reasons: list[str]
    policy_snapshot: dict
    capability_decisions: dict | list
    readiness_state: str = Field(pattern=GOVERNANCE_AUTOPILOT_READINESS_STATE_PATTERN)
    ready_for_runner: bool
    caveat: str


class GovernanceAutopilotExecutionIntentReadinessResponse(BaseModel):
    intent_id: UUID
    intent_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_INTENT_STATUS_PATTERN)
    latest_approval_id: UUID | None = None
    latest_approval_status: str | None = Field(default=None, pattern=GOVERNANCE_AUTOPILOT_APPROVAL_STATUS_PATTERN)
    readiness_state: str = Field(pattern=GOVERNANCE_AUTOPILOT_READINESS_STATE_PATTERN)
    ready_for_runner: bool
    blocked_reasons: list[str]
    approval_required: bool
    quorum_met: bool = False
    rejection_threshold_met: bool = False
    approval_vote_count: int = 0
    rejection_vote_count: int = 0
    capability_summary: dict
    caveat: str


class GovernanceAutopilotExecutionApprovalSummary(BaseModel):
    total_approvals: int
    by_status: dict[str, int]
    ready_for_runner_count: int
    approval_required_count: int
    blocked_count: int
    latest_approval_at: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerHandoffPreviewRequest(BaseModel):
    approval_id: UUID | None = None


class GovernanceAutopilotRunnerInterfaceContractResponse(BaseModel):
    handoff_schema_version: str
    required_fields: list[str]
    supported_source_types: list[str]
    supported_statuses: list[str]
    idempotency_rules: dict
    dry_run_only: bool
    execution_allowed: bool
    caveat: str


class GovernanceAutopilotRunnerSimulationCreate(BaseModel):
    approval_id: UUID | None = None
    idempotency_key: str | None = None


class GovernanceAutopilotRunnerHandoffPreviewResponse(BaseModel):
    execution_intent_id: UUID
    approval_id: UUID | None = None
    simulation_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_SIMULATION_STATUS_PATTERN)
    handoff_payload_json: dict | list
    readiness_snapshot_json: dict | list
    policy_snapshot_json: dict | list
    capability_snapshot_json: dict | list
    source_hash: str
    idempotency_key: str
    dry_run: bool
    execution_allowed: bool
    caveat: str


class GovernanceAutopilotRunnerSimulationRead(UUIDTimestampSchema):
    simulation_id: UUID | None = None
    organization_id: UUID
    execution_intent_id: UUID
    approval_id: UUID | None = None
    simulation_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_SIMULATION_STATUS_PATTERN)
    handoff_payload_json: dict | list
    readiness_snapshot_json: dict | list
    policy_snapshot_json: dict | list
    capability_snapshot_json: dict | list
    source_hash: str
    idempotency_key: str
    simulation_sha256: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerSimulationArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotRunnerSimulationSummary(BaseModel):
    total_simulations: int
    by_status: dict[str, int]
    ready_for_runner_count: int
    blocked_count: int
    approval_required_count: int
    latest_simulation_at: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerHandoffVerifyRequest(BaseModel):
    handoff_payload_json: dict


class GovernanceAutopilotRunnerHandoffVerifyResponse(BaseModel):
    valid: bool
    validation_errors: list[str]
    caveat: str


class GovernanceAutopilotRunnerAdmissionPreviewRequest(BaseModel):
    token_expires_at: datetime | None = None


class GovernanceAutopilotRunnerAdmissionPreviewResponse(BaseModel):
    simulation_id: UUID
    execution_intent_id: UUID
    approval_id: UUID | None = None
    would_admit: bool
    proposed_admission_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_ADMISSION_STATUS_PATTERN)
    consistency_checks_json: dict | list
    readiness_snapshot_json: dict | list
    blocked_reasons: list[str]
    idempotency_key: str
    token_expiration_preview: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerAdmissionCreateRequest(BaseModel):
    token_expires_at: datetime | None = None


class GovernanceAutopilotRunnerAdmissionRead(UUIDTimestampSchema):
    admission_id: UUID
    organization_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    approval_id: UUID | None = None
    admission_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_ADMISSION_STATUS_PATTERN)
    readiness_snapshot_json: dict | list
    consistency_checks_json: dict | list
    handoff_payload_json: dict | list
    handoff_token_fingerprint: str | None = None
    idempotency_key: str
    token_expires_at: datetime | None = None
    admitted_by_user_id: UUID | None = None
    revoked_by_user_id: UUID | None = None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    archived_at: datetime | None = None
    caveat: str
    handoff_token: str | None = None


class GovernanceAutopilotRunnerAdmissionTokenVerifyRequest(BaseModel):
    handoff_token: str = Field(min_length=1, max_length=2048)


class GovernanceAutopilotRunnerAdmissionTokenVerifyResponse(BaseModel):
    valid: bool
    expired: bool
    admission_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_ADMISSION_STATUS_PATTERN)
    validation_errors: list[str]
    caveat: str


class GovernanceAutopilotRunnerAdmissionRevokeRequest(BaseModel):
    revoke_reason: str = Field(min_length=1, max_length=2000)


class GovernanceAutopilotRunnerAdmissionArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotRunnerAdmissionSummary(BaseModel):
    total_admissions: int
    by_status: dict[str, int]
    admitted_count: int
    blocked_count: int
    revoked_count: int
    expired_count: int
    latest_admission_at: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerSessionPreviewRequest(BaseModel):
    handoff_token: str = Field(min_length=1, max_length=2048)
    expires_at: datetime | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=1000)
    replay_window_seconds: int | None = Field(default=None, ge=1, le=86400)


class GovernanceAutopilotRunnerSessionPreviewResponse(BaseModel):
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    would_create_session: bool
    proposed_session_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_SESSION_STATUS_PATTERN)
    binding_context_json: dict | list
    expires_at: datetime
    max_attempts: int
    replay_window_seconds: int
    blocked_reasons: list[str]
    caveat: str


class GovernanceAutopilotRunnerSessionCreateRequest(BaseModel):
    handoff_token: str = Field(min_length=1, max_length=2048)
    expires_at: datetime | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=1000)
    replay_window_seconds: int | None = Field(default=None, ge=1, le=86400)


class GovernanceAutopilotRunnerSessionRead(UUIDTimestampSchema):
    session_id: UUID
    organization_id: UUID
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    session_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_SESSION_STATUS_PATTERN)
    admission_token_fingerprint: str | None = None
    session_token_fingerprint: str | None = None
    lease_payload_json: dict | list
    binding_context_json: dict | list
    attempt_count: int
    max_attempts: int
    replay_window_seconds: int
    expires_at: datetime
    last_verified_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None
    revoke_reason: str | None = None
    archived_at: datetime | None = None
    created_by_user_id: UUID | None = None
    caveat: str
    session_token: str | None = None


class GovernanceAutopilotRunnerSessionVerifyRequest(BaseModel):
    session_token: str = Field(min_length=1, max_length=2048)


class GovernanceAutopilotRunnerSessionVerifyResponse(BaseModel):
    valid: bool
    expired: bool
    session_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_SESSION_STATUS_PATTERN)
    attempt_count: int
    max_attempts: int
    replay_window_seconds: int
    validation_errors: list[str]
    last_verified_at: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerSessionRevokeRequest(BaseModel):
    revoke_reason: str = Field(min_length=1, max_length=2000)


class GovernanceAutopilotRunnerSessionArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotRunnerSessionSummary(BaseModel):
    total_sessions: int
    by_status: dict[str, int]
    active_count: int
    expired_count: int
    locked_count: int
    revoked_count: int
    latest_session_at: datetime | None = None
    caveat: str


class GovernanceAutopilotRunnerSessionExpireStaleResponse(BaseModel):
    expired_count: int
    expired_session_ids: list[UUID]
    caveat: str


class GovernanceAutopilotRunnerHandshakeContractResponse(BaseModel):
    handshake_schema_version: str
    required_fields: list[str]
    supported_statuses: list[str]
    token_requirements: dict
    idempotency_rules: dict
    dry_run_only: bool
    execution_allowed: bool
    caveat: str


class GovernanceAutopilotRunnerHandshakePreviewRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class GovernanceAutopilotRunnerHandshakePreviewResponse(BaseModel):
    runner_session_id: UUID
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    would_create_handshake: bool
    proposed_handshake_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_HANDSHAKE_STATUS_PATTERN)
    handshake_payload_json: dict | list
    blocked_reasons: list[str]
    idempotency_key: str
    caveat: str


class GovernanceAutopilotRunnerHandshakeCreateRequest(BaseModel):
    session_token: str = Field(min_length=1, max_length=2048)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class GovernanceAutopilotRunnerHandshakeRead(UUIDTimestampSchema):
    handshake_id: UUID
    organization_id: UUID
    runner_session_id: UUID
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    handshake_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_RUNNER_HANDSHAKE_STATUS_PATTERN)
    handshake_payload_json: dict | list
    session_verification_snapshot_json: dict | list
    admission_snapshot_json: dict | list
    simulation_snapshot_json: dict | list
    intent_snapshot_json: dict | list
    idempotency_key: str
    handshake_fingerprint: str | None = None
    handshake_sha256: str
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None
    revoke_reason: str | None = None
    archived_at: datetime | None = None
    created_by_user_id: UUID | None = None
    caveat: str


class GovernanceAutopilotRunnerHandshakeVerifyRequest(BaseModel):
    handshake_payload_json: dict | list | None = None


class GovernanceAutopilotRunnerHandshakeVerifyResponse(BaseModel):
    valid: bool
    validation_errors: list[str]
    caveat: str


class GovernanceAutopilotRunnerHandshakeRevokeRequest(BaseModel):
    revoke_reason: str = Field(min_length=1, max_length=2000)


class GovernanceAutopilotRunnerHandshakeArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotRunnerHandshakeSummary(BaseModel):
    total_handshakes: int
    by_status: dict[str, int]
    ready_for_future_runner_count: int
    blocked_count: int
    revoked_count: int
    archived_count: int
    latest_handshake_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerContractResponse(BaseModel):
    noop_runner_schema_version: str
    noop_only: bool
    dry_run: bool
    execution_allowed: bool
    real_runner_present: bool = False
    job_queue_present: bool = False
    safety_flags: dict[str, bool] | None = None
    supported_event_types: list[str]
    required_fields: list[str]
    idempotency_rules: dict
    caveat: str


class GovernanceAutopilotNoopRunnerEventPreviewRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class GovernanceAutopilotNoopRunnerEventPreviewResponse(BaseModel):
    runner_handshake_id: UUID
    runner_session_id: UUID
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    would_log_event: bool
    proposed_event_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_PATTERN)
    event_payload_json: dict | list
    noop_result_json: dict | list
    blocked_reasons: list[str]
    idempotency_key: str
    caveat: str


class GovernanceAutopilotNoopRunnerEventCreateRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class GovernanceAutopilotNoopRunnerEventRead(UUIDTimestampSchema):
    event_id: UUID
    organization_id: UUID
    runner_handshake_id: UUID
    runner_session_id: UUID
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    event_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_PATTERN)
    event_type: str = Field(pattern=GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_TYPE_PATTERN)
    noop_only: bool
    dry_run: bool
    execution_allowed: bool
    idempotency_key: str
    event_payload_json: dict | list
    noop_result_json: dict | list
    source_hash: str
    event_sha256: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerEventVerifyRequest(BaseModel):
    event_payload_json: dict | list | None = None


class GovernanceAutopilotNoopRunnerEventVerifyResponse(BaseModel):
    valid: bool
    validation_errors: list[str]
    caveat: str


class GovernanceAutopilotNoopRunnerEventArchiveRequest(BaseModel):
    reason: str | None = None


class GovernanceAutopilotNoopRunnerEventSummary(BaseModel):
    total_events: int
    by_status: dict[str, int]
    logged_count: int
    blocked_count: int
    archived_count: int
    latest_event_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerLedgerRow(BaseModel):
    event_id: UUID
    event_status: str = Field(pattern=GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_PATTERN)
    event_type: str = Field(pattern=GOVERNANCE_AUTOPILOT_NOOP_RUNNER_EVENT_TYPE_PATTERN)
    runner_handshake_id: UUID
    runner_session_id: UUID
    runner_admission_id: UUID
    runner_simulation_id: UUID
    execution_intent_id: UUID
    noop_only: bool
    dry_run: bool
    execution_allowed: bool
    idempotency_key: str
    blocked_reasons: list[str]
    source_hash: str
    event_sha256: str
    created_at: datetime
    caveat: str


class GovernanceAutopilotNoopRunnerTimelineBucket(BaseModel):
    day: str
    total_count: int
    logged_count: int
    blocked_count: int
    archived_count: int


class GovernanceAutopilotNoopRunnerTimelineReport(BaseModel):
    total_events: int
    timeline_buckets: list[GovernanceAutopilotNoopRunnerTimelineBucket]
    logged_count: int
    blocked_count: int
    archived_count: int
    latest_event_at: datetime | None = None
    report_schema_version: str | None = None
    generated_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerTopBlocker(BaseModel):
    reason: str
    count: int


class GovernanceAutopilotNoopRunnerBlockerReport(BaseModel):
    total_blocked_events: int
    blocker_counts: dict[str, int]
    top_blockers: list[GovernanceAutopilotNoopRunnerTopBlocker]
    affected_execution_intents: list[UUID]
    report_schema_version: str | None = None
    generated_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerReadinessReport(BaseModel):
    ready_handshake_count: int
    no_op_logged_count: int
    blocked_event_count: int
    no_event_for_ready_handshake_count: int
    latest_ready_handshake_at: datetime | None = None
    latest_noop_event_at: datetime | None = None
    report_schema_version: str | None = None
    generated_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerIdempotencyReport(BaseModel):
    total_events: int
    unique_idempotency_key_count: int
    duplicate_key_attempts_inferred_count: int
    active_duplicate_records_count: int
    idempotency_keys_with_multiple_records: list[str]
    report_schema_version: str | None = None
    generated_at: datetime | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerControlPlaneHealthReport(BaseModel):
    execution_allowed: bool = False
    real_runner_present: bool = False
    job_queue_present: bool = False
    noop_runner_only: bool = True
    total_noop_events: int
    blocked_event_count: int
    readiness_gap_count: int
    token_plaintext_storage_detected: bool = False
    external_side_effects_enabled: bool = False
    health_status: str = Field(pattern="^(healthy|warning|attention_required)$")
    health_reasons: list[str]
    report_schema_version: str | None = None
    generated_at: datetime | None = None
    report_type: str | None = None
    query_hash: str | None = None
    result_hash: str | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerReportsContractResponse(BaseModel):
    report_schema_version: str
    supported_report_types: list[str]
    common_metadata_fields: list[str]
    compatibility_policy_version: str
    compatibility_policy_endpoint: str
    breaking_changes_require_new_schema_version: bool
    additive_fields_allowed: bool
    minimum_supported_schema_version: str
    current_supported_schema_version: str
    filter_options_endpoint: str | None = None
    pagination_contract_endpoint: str | None = None
    client_contract_endpoint: str | None = None
    field_docs_endpoint: str | None = None
    display_metadata_endpoint: str | None = None
    localization_map_endpoint: str | None = None
    client_hints_endpoint: str | None = None
    bounded_export_limits: dict
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerDiagnosticsManifestResponse(BaseModel):
    report_schema_version: str
    compatibility_policy_version: str
    compatibility_policy_endpoint: str
    minimum_supported_schema_version: str
    current_supported_schema_version: str
    filter_options_endpoint: str | None = None
    pagination_contract_endpoint: str | None = None
    client_contract_endpoint: str | None = None
    field_docs_endpoint: str | None = None
    display_metadata_endpoint: str | None = None
    localization_map_endpoint: str | None = None
    client_hints_endpoint: str | None = None
    available_reports: list[str]
    endpoint_map: dict[str, str]
    safety_flags: dict[str, bool]
    execution_allowed: bool = False
    real_runner_present: bool = False
    job_queue_present: bool = False
    noop_runner_only: bool = True
    latest_noop_event_at: datetime | None = None
    total_noop_events: int
    known_limitations: list[str]
    caveat: str


class GovernanceAutopilotNoopRunnerBoundedExportResponse(BaseModel):
    report_schema_version: str
    report_type: str
    generated_at: datetime
    query: dict | list
    query_hash: str
    result_hash: str
    limit: int
    offset: int
    truncated: bool
    next_offset: int | None = None
    row_count: int
    pagination: dict | None = None
    rows: list[dict] | None = None
    report_payload: dict | list | None = None
    safety_flags: dict[str, bool]
    execution_allowed: bool = False
    real_runner_present: bool = False
    job_queue_present: bool = False
    noop_runner_only: bool = True
    caveat: str


class GovernanceAutopilotNoopRunnerReportChecksumResponse(BaseModel):
    report_type: str
    query_hash: str
    result_hash: str
    row_count: int
    generated_at: datetime
    caveat: str


class GovernanceAutopilotNoopRunnerCompatibilityPolicyResponse(BaseModel):
    report_schema_version: str
    compatibility_policy_version: str
    additive_fields_allowed: bool
    breaking_changes_require_new_schema_version: bool
    deprecated_fields_policy: str
    minimum_supported_schema_version: str
    current_supported_schema_version: str
    stable_endpoint_families: list[str]
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerClientContractResponse(BaseModel):
    client_contract_version: str
    report_schema_version: str
    compatibility_policy_version: str
    stable_endpoint_families: list[str]
    supported_filters_by_endpoint: dict[str, list[str]]
    pagination_contract: dict
    enum_values: dict[str, list[str]]
    default_limits: dict
    max_limits: dict
    field_docs_endpoint: str | None = None
    display_metadata_endpoint: str | None = None
    localization_map_endpoint: str | None = None
    client_hints_endpoint: str | None = None
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerFilterOptionsResponse(BaseModel):
    report_schema_version: str
    supported_report_types: list[str]
    supported_event_statuses: list[str]
    supported_event_types: list[str]
    supported_boolean_filters: list[str]
    supported_id_filters: list[str]
    supported_pagination_params: list[str]
    default_values: dict
    bounds: dict
    field_docs_endpoint: str | None = None
    display_metadata_endpoint: str | None = None
    client_hints_endpoint: str | None = None
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerPaginationContractResponse(BaseModel):
    pagination_contract_version: str
    supported_style: str
    default_limit: int
    max_limit: int
    offset_base: int
    response_fields: list[str]
    truncation_behavior: str
    field_docs_endpoint: str | None = None
    display_metadata_endpoint: str | None = None
    client_hints_endpoint: str | None = None
    safety_flags: dict[str, bool] | None = None
    caveat: str


class GovernanceAutopilotNoopRunnerFieldDocsResponse(BaseModel):
    field_docs_version: str
    report_schema_version: str
    compatibility_policy_version: str
    report_type: str | None = None
    field_docs: dict | list
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerDisplayMetadataResponse(BaseModel):
    display_metadata_version: str
    report_schema_version: str
    report_type: str | None = None
    table_columns: dict | list
    default_sort: dict
    recommended_grouping: list[str]
    empty_state: dict
    severity_mapping: dict[str, str]
    status_badges: dict[str, dict]
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerLocalizationMapResponse(BaseModel):
    localization_map_version: str
    default_locale: str
    supported_locales: list[str]
    keys: dict[str, str]
    safety_flags: dict[str, bool]
    caveat: str


class GovernanceAutopilotNoopRunnerClientHintsResponse(BaseModel):
    client_hints_version: str
    recommended_refresh_seconds: int
    cache_policy: str
    pagination_hints: dict
    filter_hints: dict
    empty_state_hints: dict
    safety_flags: dict[str, bool]
    caveat: str


class AISystemRiskRefreshClassificationSignalsRequest(BaseModel):
    persist_signals: bool = False


class AISystemRiskRefreshClassificationSignalsResponse(BaseModel):
    persist_signals: bool
    candidate_count: int
    created_count: int
    created_signal_ids: list[str] | None = None
    signals: list[dict]
    caveat: str


class AISystemRiskClassificationSummary(BaseModel):
    total_classifications: int
    active_classifications: int
    superseded_classifications: int
    archived_classifications: int
    by_confidence_level: dict[str, int]
    by_source_type: dict[str, int]
    by_label_group: dict[str, int]
    assessments_with_classifications: int
    assessments_without_classifications: int
    default_taxonomy_id: UUID | None = None
    caveat: str


class AISystemControlLinkCreate(BaseModel):
    control_id: UUID
    link_reason: str | None = None


class AISystemControlLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    ai_system_id: UUID
    control_id: UUID
    status: str
    link_reason: str | None = None
    created_by_user_id: UUID | None = None
    unlinked_by_user_id: UUID | None = None
    unlinked_at: datetime | None = None
    unlink_reason: str | None = None


class AISystemEvidenceLinkCreate(BaseModel):
    evidence_id: UUID
    link_reason: str | None = None


class AISystemEvidenceLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    ai_system_id: UUID
    evidence_id: UUID
    status: str
    link_reason: str | None = None
    created_by_user_id: UUID | None = None
    unlinked_by_user_id: UUID | None = None
    unlinked_at: datetime | None = None
    unlink_reason: str | None = None


class AISystemRiskLinkCreate(BaseModel):
    risk_id: UUID
    link_reason: str | None = None


class AISystemRiskLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    ai_system_id: UUID
    risk_id: UUID
    status: str
    link_reason: str | None = None
    created_by_user_id: UUID | None = None
    unlinked_by_user_id: UUID | None = None
    unlinked_at: datetime | None = None
    unlink_reason: str | None = None


class AISystemUnlinkRequest(BaseModel):
    unlink_reason: str = Field(min_length=1, max_length=2000)


class AISystemLinksSummary(BaseModel):
    active_control_links: int
    active_evidence_links: int
    active_risk_links: int
    unlinked_control_links: int
    unlinked_evidence_links: int
    unlinked_risk_links: int
    total_active_links: int
    total_unlinked_links: int


REVIEW_TYPE_PATTERN = "^(initial_review|pre_production_review|periodic_review|change_review|retirement_review)$"
REVIEW_STATUS_PATTERN = "^(pending|in_progress|completed|cancelled)$"
REVIEW_OUTCOME_PATTERN = "^(approved|approved_with_conditions|needs_changes|rejected|not_applicable)$"
ATTESTATION_DECISION_PATTERN = "^(attest|reject|acknowledge)$"
REVIEW_REMINDER_POLICY_STATUS_PATTERN = "^(active|inactive|archived)$"
REVIEW_EVENT_TYPE_PATTERN = "^(reminder_due|review_overdue|escalation_due)$"
REVIEW_EVENT_STATUS_PATTERN = "^(open|resolved|dismissed)$"
REVIEW_RECURRENCE_CADENCE_PATTERN = "^(days|weeks|months|quarters|years)$"
REVIEW_RECURRENCE_TEMPLATE_STATUS_PATTERN = "^(active|inactive|archived)$"
REVIEW_PLAN_RUN_STATUS_PATTERN = "^(previewed|applied|failed)$"
REVIEW_PLAN_CONSTRAINT_TYPE_PATTERN = "^(prerequisite_completed|prerequisite_window)$"
REVIEW_PLAN_CONSTRAINT_ENFORCEMENT_PATTERN = "^(warn|block)$"
REVIEW_PLAN_CONSTRAINT_STATUS_PATTERN = "^(active|inactive|archived)$"
SEQUENCE_PACK_STATUS_PATTERN = "^(active|inactive|archived)$"
SEQUENCE_STEP_STATUS_PATTERN = "^(active|inactive|archived)$"
SEQUENCE_RUN_STATUS_PATTERN = "^(previewed|applied|failed)$"
FREEZE_WINDOW_STATUS_PATTERN = "^(active|inactive|archived)$"
FREEZE_WINDOW_SCOPE_TYPE_PATTERN = "^(all_ai_governance|review_type|sequence_pack|ai_system)$"
FREEZE_WINDOW_ENFORCEMENT_LEVEL_PATTERN = "^(info|warn|block)$"
OPERATOR_ACK_ACTION_TYPE_PATTERN = "^(sequence_apply|recurrence_plan_apply)$"
OPERATOR_ACK_TARGET_TYPE_PATTERN = "^(sequence_pack|recurrence_template|review_plan)$"
GUARDRAIL_POLICY_SET_STATUS_PATTERN = "^(active|inactive|archived)$"
GUARDRAIL_POLICY_SET_VERSION_STATUS_PATTERN = "^(draft|active|deprecated|archived)$"
GUARDRAIL_POLICY_ASSIGNMENT_SCOPE_PATTERN = "^(all_ai_governance|sequence_pack|rollout_class|review_type|ai_system)$"
GUARDRAIL_POLICY_ASSIGNMENT_STATUS_PATTERN = "^(active|inactive|archived)$"
GUARDRAIL_POLICY_ASSIGNMENT_EVENT_PATTERN = "^(created|updated|archived)$"
POLICY_RESOLUTION_SIM_REPORT_STATUS_PATTERN = "^(generated|archived)$"
POLICY_RESOLUTION_SIM_DIFF_REPORT_STATUS_PATTERN = "^(generated|archived)$"
POLICY_RESOLUTION_SIM_DIFF_MATCH_STRATEGY_PATTERN = "^(context_key_then_index|context_key_only)$"
POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN = "^(active|inactive|archived)$"
POLICY_DIFF_GATING_REPORT_STATUS_PATTERN = "^(generated|archived)$"
POLICY_DIFF_GATING_SEVERITY_PATTERN = "^(info|low|medium|high|critical)$"
POLICY_DIFF_GATING_COMPARE_REPORT_STATUS_PATTERN = "^(generated|archived)$"
POLICY_DIFF_GATING_COMPARE_SEVERITY_DIRECTION_PATTERN = "^(increased|decreased|unchanged)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_REPORT_STATUS_PATTERN = "^(generated|archived)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_MAX_SEVERITY_DRIFT_PATTERN = "^(increased|decreased|unchanged)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_REVIEW_REQUIRED_DRIFT_PATTERN = "^(became_required|became_not_required|unchanged)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN = "^(active|inactive|archived)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_REPORT_STATUS_PATTERN = "^(generated|archived)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PATTERN = (
    "^(all_ai_governance|export_type|diagnostic_export_diff_gating_profile|"
    "diagnostic_export_diff_gating_compare_report|sequence_pack|ai_system|review_type|rollout_class)$"
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_STATUS_PATTERN = "^(active|inactive|archived)$"
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_EVENT_PATTERN = "^(created|updated|archived)$"
POLICY_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN = "^(active|inactive|archived)$"
POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_STATUS_PATTERN = "^(draft|active|deprecated|archived)$"
POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN = "^(active_then_mutable|pinned_preferred|pinned_required)$"
POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN = "^(stable|attention|review_required|critical_review)$"
POLICY_DIFF_GATING_COMPARE_PRESET_REPORT_STATUS_PATTERN = "^(generated|archived)$"


class AISystemGovernanceReviewCreate(BaseModel):
    review_type: str = Field(pattern=REVIEW_TYPE_PATTERN)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    checklist_json: dict | list | None = None
    assigned_to_user_id: UUID | None = None


class AISystemGovernanceReviewComplete(BaseModel):
    outcome: str = Field(pattern=REVIEW_OUTCOME_PATTERN)
    findings_json: dict | list | None = None
    conditions_json: dict | list | None = None
    checklist_json: dict | list | None = None


class AISystemGovernanceReviewCancel(BaseModel):
    cancellation_reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernanceReviewRead(UUIDTimestampSchema):
    organization_id: UUID
    ai_system_id: UUID
    review_type: str
    status: str
    outcome: str | None = None
    title: str
    description: str | None = None
    checklist_json: dict | list | None = None
    findings_json: dict | list | None = None
    conditions_json: dict | list | None = None
    requested_by_user_id: UUID | None = None
    assigned_to_user_id: UUID | None = None
    started_by_user_id: UUID | None = None
    started_at: datetime | None = None
    completed_by_user_id: UUID | None = None
    completed_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    caveat: str | None = None
    due_at: datetime | None = None
    reminder_policy_id: UUID | None = None
    last_reminder_at: datetime | None = None
    escalated_at: datetime | None = None


class AISystemGovernanceReviewScheduleRequest(BaseModel):
    due_at: datetime
    reminder_policy_id: UUID | None = None


class AISystemGovernanceAttestationCreate(BaseModel):
    decision: str = Field(pattern=ATTESTATION_DECISION_PATTERN)
    statement: str = Field(min_length=1, max_length=5000)


class AISystemGovernanceAttestationRead(BaseModel):
    id: UUID
    organization_id: UUID
    ai_system_id: UUID
    review_id: UUID
    signer_user_id: UUID | None = None
    signer_role_name: str | None = None
    decision: str
    statement: str
    checklist_snapshot_json: dict | list | None = None
    review_snapshot_json: dict | list | None = None
    content_sha256: str
    signature_algorithm: str
    internal_signature: str
    signed_at: datetime
    caveat: str | None = None
    created_at: datetime


class AISystemGovernanceAttestationVerifyResponse(BaseModel):
    valid_hash: bool
    valid_signature: bool
    content_sha256: str
    recomputed_sha256: str
    signature_algorithm: str
    caveat: str


class AISystemGovernanceSummary(BaseModel):
    total_reviews: int
    pending_reviews: int
    in_progress_reviews: int
    completed_reviews: int
    cancelled_reviews: int
    by_review_type: dict[str, int]
    by_outcome: dict[str, int]
    total_attestations: int
    latest_review_at: datetime | None = None
    latest_attestation_at: datetime | None = None


class AISystemGovernanceReviewReminderPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    review_type: str | None = Field(default=None, pattern=REVIEW_TYPE_PATTERN)
    days_before_due: int = Field(default=0, ge=0)
    overdue_after_days: int = Field(default=0, ge=0)
    escalation_after_days: int = Field(default=0, ge=0)
    notify_assignee: bool = False
    status: str = Field(default="active", pattern=REVIEW_REMINDER_POLICY_STATUS_PATTERN)


class AISystemGovernanceReviewReminderPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    review_type: str | None = Field(default=None, pattern=REVIEW_TYPE_PATTERN)
    days_before_due: int | None = Field(default=None, ge=0)
    overdue_after_days: int | None = Field(default=None, ge=0)
    escalation_after_days: int | None = Field(default=None, ge=0)
    notify_assignee: bool | None = None
    status: str | None = Field(default=None, pattern=REVIEW_REMINDER_POLICY_STATUS_PATTERN)


class AISystemGovernanceReviewReminderPolicyRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    review_type: str | None = None
    days_before_due: int
    overdue_after_days: int
    escalation_after_days: int
    notify_assignee: bool
    status: str
    created_by_user_id: UUID | None = None


class AISystemGovernanceReviewQueueItem(BaseModel):
    review_id: UUID
    ai_system_id: UUID
    review_type: str
    status: str
    title: str
    assigned_to_user_id: UUID | None = None
    due_at: datetime
    reminder_policy_id: UUID | None = None
    reminder_policy_name: str | None = None
    days_before_due: int
    overdue_after_days: int
    escalation_after_days: int
    reminder_due_at: datetime
    overdue_at: datetime
    escalation_at: datetime
    is_due_soon: bool
    is_overdue: bool
    is_escalation_due: bool
    last_reminder_at: datetime | None = None
    escalated_at: datetime | None = None


class AISystemGovernanceReviewScheduleEvaluateRequest(BaseModel):
    dry_run: bool = True
    notify: bool = False


class AISystemGovernanceReviewScheduleEvaluateResponse(BaseModel):
    dry_run: bool
    would_create_count: int
    created_count: int
    queued_email_count: int
    would_create: list[dict]
    created_event_ids: list[str]
    queued_email_ids: list[str]


class AISystemGovernanceReviewEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    ai_system_id: UUID
    review_id: UUID
    event_type: str
    status: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    resolved_by_user_id: UUID | None = None
    resolution_notes: str | None = None
    details_json: dict | list | None = None
    created_at: datetime


class AISystemGovernanceReviewEventResolveRequest(BaseModel):
    resolution_notes: str | None = None


class AISystemGovernanceReviewScheduleSummary(BaseModel):
    scheduled_reviews: int
    unscheduled_reviews: int
    due_soon_reviews: int
    overdue_reviews: int
    escalated_reviews: int
    open_events: int
    resolved_events: int
    by_event_type: dict[str, int]


class AISystemGovernanceReviewRecurrenceTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    review_type: str = Field(pattern=REVIEW_TYPE_PATTERN)
    cadence_type: str = Field(pattern=REVIEW_RECURRENCE_CADENCE_PATTERN)
    interval_value: int = Field(gt=0)
    default_reminder_policy_id: UUID | None = None
    default_assigned_to_user_id: UUID | None = None
    default_checklist_json: dict | list | None = None
    default_description: str | None = None
    status: str = Field(default="active", pattern=REVIEW_RECURRENCE_TEMPLATE_STATUS_PATTERN)


class AISystemGovernanceReviewRecurrenceTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    review_type: str | None = Field(default=None, pattern=REVIEW_TYPE_PATTERN)
    cadence_type: str | None = Field(default=None, pattern=REVIEW_RECURRENCE_CADENCE_PATTERN)
    interval_value: int | None = Field(default=None, gt=0)
    default_reminder_policy_id: UUID | None = None
    default_assigned_to_user_id: UUID | None = None
    default_checklist_json: dict | list | None = None
    default_description: str | None = None
    status: str | None = Field(default=None, pattern=REVIEW_RECURRENCE_TEMPLATE_STATUS_PATTERN)


class AISystemGovernanceReviewRecurrenceTemplateArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceReviewRecurrenceTemplateRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    review_type: str
    cadence_type: str
    interval_value: int
    default_reminder_policy_id: UUID | None = None
    default_assigned_to_user_id: UUID | None = None
    default_checklist_json: dict | list | None = None
    default_description: str | None = None
    status: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceReviewPlanGenerateRequest(BaseModel):
    dry_run: bool = True
    horizon_days: int = Field(default=365, ge=1, le=1095)
    ai_system_ids: list[UUID] | None = None
    start_from: datetime | date_type | None = None
    apply_constraints: bool = True
    constraint_ids: list[UUID] | None = None


class AISystemGovernanceReviewPlanItem(BaseModel):
    ai_system_id: UUID
    review_type: str
    title: str
    due_at: datetime
    assigned_to_user_id: UUID | None = None
    reminder_policy_id: UUID | None = None
    constraint_results: list[dict] | None = None


class AISystemGovernanceReviewPlanSkippedItem(BaseModel):
    ai_system_id: UUID
    review_type: str
    due_at: datetime
    reason: str
    constraint_results: list[dict] | None = None


class AISystemGovernanceReviewPlanGenerateResponse(BaseModel):
    dry_run: bool
    template_id: UUID
    horizon_days: int
    planned_count: int
    created_count: int
    skipped_count: int
    planned_reviews: list[AISystemGovernanceReviewPlanItem]
    skipped_reviews: list[AISystemGovernanceReviewPlanSkippedItem]
    run_id: UUID | None = None
    caveat: str


class AISystemGovernanceReviewPlanRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    template_id: UUID
    status: str
    dry_run: bool
    horizon_days: int
    target_ai_system_ids_json: list[str] | None = None
    generated_reviews_count: int
    skipped_reviews_count: int
    result_json: dict | list
    requested_by_user_id: UUID | None = None
    created_at: datetime


class AISystemGovernanceReviewRecurrenceSummary(BaseModel):
    active_templates: int
    inactive_templates: int
    archived_templates: int
    plan_runs: int
    applied_plan_runs: int
    previewed_plan_runs: int
    generated_reviews_last_30d: int
    skipped_reviews_last_30d: int


class AISystemGovernanceReviewPlanConstraintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    target_review_type: str = Field(pattern=REVIEW_TYPE_PATTERN)
    prerequisite_review_type: str = Field(pattern=REVIEW_TYPE_PATTERN)
    constraint_type: str = Field(pattern=REVIEW_PLAN_CONSTRAINT_TYPE_PATTERN)
    enforcement_mode: str = Field(pattern=REVIEW_PLAN_CONSTRAINT_ENFORCEMENT_PATTERN)
    min_gap_days: int | None = Field(default=None, ge=0)
    max_gap_days: int | None = Field(default=None, ge=0)
    status: str = Field(default="active", pattern=REVIEW_PLAN_CONSTRAINT_STATUS_PATTERN)


class AISystemGovernanceReviewPlanConstraintUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    target_review_type: str | None = Field(default=None, pattern=REVIEW_TYPE_PATTERN)
    prerequisite_review_type: str | None = Field(default=None, pattern=REVIEW_TYPE_PATTERN)
    constraint_type: str | None = Field(default=None, pattern=REVIEW_PLAN_CONSTRAINT_TYPE_PATTERN)
    enforcement_mode: str | None = Field(default=None, pattern=REVIEW_PLAN_CONSTRAINT_ENFORCEMENT_PATTERN)
    min_gap_days: int | None = Field(default=None, ge=0)
    max_gap_days: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern=REVIEW_PLAN_CONSTRAINT_STATUS_PATTERN)


class AISystemGovernanceReviewPlanConstraintArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceReviewPlanConstraintRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    target_review_type: str
    prerequisite_review_type: str
    constraint_type: str
    enforcement_mode: str
    min_gap_days: int | None = None
    max_gap_days: int | None = None
    status: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceReviewPlanConstraintSummary(BaseModel):
    active_constraints: int
    inactive_constraints: int
    archived_constraints: int
    block_constraints: int
    warn_constraints: int
    by_constraint_type: dict[str, int]
    by_target_review_type: dict[str, int]


class AISystemGovernanceReviewSequencePackCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="active", pattern=SEQUENCE_PACK_STATUS_PATTERN)


class AISystemGovernanceReviewSequencePackUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=SEQUENCE_PACK_STATUS_PATTERN)


class AISystemGovernanceReviewSequencePackArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceReviewSequencePackRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceReviewSequenceStepCreate(BaseModel):
    step_order: int = Field(gt=0)
    review_type: str = Field(pattern=REVIEW_TYPE_PATTERN)
    title_template: str | None = Field(default=None, max_length=255)
    description_template: str | None = None
    offset_days_from_start: int = Field(ge=0)
    default_reminder_policy_id: UUID | None = None
    default_assigned_to_user_id: UUID | None = None
    default_checklist_json: dict | list | None = None
    require_previous_step_planned: bool = True
    status: str = Field(default="active", pattern=SEQUENCE_STEP_STATUS_PATTERN)


class AISystemGovernanceReviewSequenceStepUpdate(BaseModel):
    step_order: int | None = Field(default=None, gt=0)
    review_type: str | None = Field(default=None, pattern=REVIEW_TYPE_PATTERN)
    title_template: str | None = Field(default=None, max_length=255)
    description_template: str | None = None
    offset_days_from_start: int | None = Field(default=None, ge=0)
    default_reminder_policy_id: UUID | None = None
    default_assigned_to_user_id: UUID | None = None
    default_checklist_json: dict | list | None = None
    require_previous_step_planned: bool | None = None
    status: str | None = Field(default=None, pattern=SEQUENCE_STEP_STATUS_PATTERN)


class AISystemGovernanceReviewSequenceStepArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceReviewSequenceStepRead(UUIDTimestampSchema):
    organization_id: UUID
    sequence_pack_id: UUID
    step_order: int
    review_type: str
    title_template: str | None = None
    description_template: str | None = None
    offset_days_from_start: int
    default_reminder_policy_id: UUID | None = None
    default_assigned_to_user_id: UUID | None = None
    default_checklist_json: dict | list | None = None
    require_previous_step_planned: bool
    status: str


class AISystemGovernanceReviewSequenceGenerateRequest(BaseModel):
    dry_run: bool = True
    ai_system_ids: list[UUID] | None = None
    start_from: datetime | date_type | None = None
    apply_constraints: bool = True
    acknowledgement_text: str | None = None
    override_freeze: bool = False
    override_reason: str | None = None
    guardrail_policy_set_id: UUID | None = None
    rollout_class: str | None = None


class AISystemGovernanceReviewSequencePlanItem(BaseModel):
    ai_system_id: UUID
    step_id: UUID
    step_order: int
    review_type: str
    title: str
    due_at: datetime
    assigned_to_user_id: UUID | None = None
    reminder_policy_id: UUID | None = None
    constraint_results: list[dict] | None = None


class AISystemGovernanceReviewSequenceSkippedItem(BaseModel):
    ai_system_id: UUID
    step_id: UUID
    step_order: int
    review_type: str
    due_at: datetime
    reason: str
    constraint_results: list[dict] | None = None


class AISystemGovernanceReviewSequenceGenerateResponse(BaseModel):
    dry_run: bool
    sequence_pack_id: UUID
    planned_count: int
    created_count: int
    skipped_count: int
    planned_reviews: list[AISystemGovernanceReviewSequencePlanItem]
    skipped_reviews: list[AISystemGovernanceReviewSequenceSkippedItem]
    run_id: UUID | None = None
    guardrail_results: dict | None = None
    caveat: str


class AISystemGovernanceReviewSequenceRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    sequence_pack_id: UUID
    status: str
    dry_run: bool
    target_ai_system_ids_json: list[str] | None = None
    start_from: datetime
    apply_constraints: bool
    generated_reviews_count: int
    skipped_reviews_count: int
    result_json: dict | list
    requested_by_user_id: UUID | None = None
    created_at: datetime


class AISystemGovernanceReviewSequenceSummary(BaseModel):
    active_packs: int
    inactive_packs: int
    archived_packs: int
    active_steps: int
    sequence_runs: int
    previewed_runs: int
    applied_runs: int
    generated_reviews_last_30d: int
    skipped_reviews_last_30d: int


class AISystemGovernanceFreezeWindowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    scope_type: str = Field(default="all_ai_governance", pattern=FREEZE_WINDOW_SCOPE_TYPE_PATTERN)
    scope_json: dict | list | None = None
    priority: int = Field(default=100, ge=0)
    enforcement_level: str = Field(default="block", pattern=FREEZE_WINDOW_ENFORCEMENT_LEVEL_PATTERN)
    override_allowed: bool = True
    precedence_notes: str | None = None
    reason: str = Field(min_length=1, max_length=5000)
    status: str = Field(default="active", pattern=FREEZE_WINDOW_STATUS_PATTERN)


class AISystemGovernanceFreezeWindowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    scope_type: str | None = Field(default=None, pattern=FREEZE_WINDOW_SCOPE_TYPE_PATTERN)
    scope_json: dict | list | None = None
    priority: int | None = Field(default=None, ge=0)
    enforcement_level: str | None = Field(default=None, pattern=FREEZE_WINDOW_ENFORCEMENT_LEVEL_PATTERN)
    override_allowed: bool | None = None
    precedence_notes: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=5000)
    status: str | None = Field(default=None, pattern=FREEZE_WINDOW_STATUS_PATTERN)


class AISystemGovernanceFreezeWindowArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceFreezeWindowRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    starts_at: datetime
    ends_at: datetime
    scope_type: str
    scope_json: dict | list | None = None
    priority: int
    enforcement_level: str
    override_allowed: bool
    precedence_notes: str | None = None
    reason: str
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceGuardrailCheckRequest(BaseModel):
    action_type: str = Field(pattern=OPERATOR_ACK_ACTION_TYPE_PATTERN)
    sequence_pack_id: UUID | None = None
    recurrence_template_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    policy_set_id: UUID | None = None
    rollout_class: str | None = None


class AISystemGovernanceGuardrailFreezeMatch(BaseModel):
    id: UUID
    name: str
    scope_type: str
    priority: int
    enforcement_level: str
    override_allowed: bool
    starts_at: datetime
    ends_at: datetime
    reason: str


class AISystemGovernanceGuardrailResolution(BaseModel):
    blocked: bool
    primary_blocking_window_id: UUID | None = None
    override_allowed: bool
    enforcement_level: str
    precedence_order: list[str]
    matching_window_count: int
    warnings: list[str]
    info: list[str]


class AISystemGovernanceGuardrailCheckResponse(BaseModel):
    blocked: bool
    matching_freeze_windows: list[AISystemGovernanceGuardrailFreezeMatch]
    resolution: AISystemGovernanceGuardrailResolution
    warnings: list[str]
    required_acknowledgement_text: str | None = None
    policy_set_id: UUID | None = None
    policy_version_id: UUID | None = None
    policy_resolution: dict | None = None
    caveat: str


class AISystemGovernanceGuardrailConflictPreviewResponse(BaseModel):
    all_matching_freeze_windows: list[AISystemGovernanceGuardrailFreezeMatch]
    sorted_precedence_order: list[str]
    primary_blocking_window: AISystemGovernanceGuardrailFreezeMatch | None = None
    final_decision: AISystemGovernanceGuardrailResolution
    policy_set_id: UUID | None = None
    policy_version_id: UUID | None = None
    policy_resolution: dict | None = None
    explanation: str
    caveat: str


class AISystemGovernanceOperatorAcknowledgementRead(BaseModel):
    id: UUID
    organization_id: UUID
    action_type: str
    target_type: str
    target_id: UUID | None = None
    acknowledgement_text: str
    reason: str | None = None
    override_freeze: bool
    freeze_window_ids_json: list[str] | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime


class AISystemGovernanceGuardrailSummary(BaseModel):
    active_freeze_windows: int
    inactive_freeze_windows: int
    archived_freeze_windows: int
    active_now_freeze_windows: int
    block_freeze_windows: int
    warn_freeze_windows: int
    info_freeze_windows: int
    override_disallowed_windows: int
    highest_priority: int
    acknowledgements_total: int
    freeze_overrides_total: int
    by_scope_type: dict[str, int]


class AISystemGovernanceGuardrailPolicySetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="active", pattern=GUARDRAIL_POLICY_SET_STATUS_PATTERN)


class AISystemGovernanceGuardrailPolicySetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=GUARDRAIL_POLICY_SET_STATUS_PATTERN)


class AISystemGovernanceGuardrailPolicySetArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceGuardrailPolicySetRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    active_version_id: UUID | None = None
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceGuardrailPolicySetVersionCreate(BaseModel):
    profile_json: dict
    change_reason: str = Field(min_length=1, max_length=5000)


class AISystemGovernanceGuardrailPolicySetVersionActivateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class AISystemGovernanceGuardrailPolicySetVersionRead(UUIDTimestampSchema):
    organization_id: UUID
    policy_set_id: UUID
    version_number: int
    status: str
    profile_json: dict
    change_reason: str
    created_by_user_id: UUID | None = None
    activated_by_user_id: UUID | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None


class AISystemGovernanceGuardrailPolicySetActiveProfileResponse(BaseModel):
    policy_set_id: UUID
    policy_set_name: str
    version_id: UUID
    version_number: int
    profile_json: dict
    caveat: str


class AISystemGovernanceGuardrailPolicySetSummary(BaseModel):
    active_policy_sets: int
    inactive_policy_sets: int
    archived_policy_sets: int
    total_versions: int
    active_versions: int
    draft_versions: int
    deprecated_versions: int
    policy_sets_without_active_version: int


class AISystemGovernanceGuardrailPolicyAssignmentCreate(BaseModel):
    policy_set_id: UUID
    scope_type: str = Field(pattern=GUARDRAIL_POLICY_ASSIGNMENT_SCOPE_PATTERN)
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int = Field(default=100, ge=0)
    reason: str = Field(min_length=1, max_length=5000)
    status: str = Field(default="active", pattern=GUARDRAIL_POLICY_ASSIGNMENT_STATUS_PATTERN)


class AISystemGovernanceGuardrailPolicyAssignmentUpdate(BaseModel):
    policy_set_id: UUID | None = None
    scope_type: str | None = Field(default=None, pattern=GUARDRAIL_POLICY_ASSIGNMENT_SCOPE_PATTERN)
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, min_length=1, max_length=5000)
    status: str | None = Field(default=None, pattern=GUARDRAIL_POLICY_ASSIGNMENT_STATUS_PATTERN)


class AISystemGovernanceGuardrailPolicyAssignmentArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class AISystemGovernanceGuardrailPolicyAssignmentRead(UUIDTimestampSchema):
    organization_id: UUID
    policy_set_id: UUID
    scope_type: str
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int
    status: str
    reason: str
    assigned_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceGuardrailPolicyAssignmentHistoryRead(BaseModel):
    id: UUID
    organization_id: UUID
    assignment_id: UUID
    event_type: str
    before_json: dict | list | None = None
    after_json: dict | list | None = None
    reason: str
    changed_by_user_id: UUID | None = None
    created_at: datetime


class AISystemGovernanceGuardrailPolicyAssignmentResolveRequest(BaseModel):
    explicit_policy_set_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None


class AISystemGovernanceGuardrailPolicyAssignmentResolveResponse(BaseModel):
    resolved_policy_set_id: UUID | None = None
    resolved_policy_version_id: UUID | None = None
    resolution_source: str
    assignment_id: UUID | None = None
    precedence_trace: list[dict]
    caveat: str


class AISystemGovernanceGuardrailPolicyAssignmentSummary(BaseModel):
    active_assignments: int
    inactive_assignments: int
    archived_assignments: int
    by_scope_type: dict[str, int]
    assignments_without_active_policy_version: int
    highest_priority: int
    caveat: str


class AISystemGovernancePolicyResolutionSimulationContext(BaseModel):
    context_key: str | None = Field(default=None, max_length=255)
    explicit_policy_set_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = Field(default=None, max_length=255)
    planned_start: datetime | None = None
    planned_end: datetime | None = None


class AISystemGovernancePolicyResolutionSimulationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    persist_report: bool = False
    contexts: list[AISystemGovernancePolicyResolutionSimulationContext] = Field(min_length=1, max_length=100)


class AISystemGovernancePolicyResolutionSimulationContextResult(BaseModel):
    context_key: str | None = None
    policy_resolution: dict
    guardrail_resolution: dict
    precedence_trace: list[dict]
    caveat: str


class AISystemGovernancePolicyResolutionSimulationResponse(BaseModel):
    persisted: bool
    report_id: UUID | None = None
    context_count: int
    blocked_contexts_count: int
    warning_contexts_count: int
    no_policy_contexts_count: int
    contexts: list[AISystemGovernancePolicyResolutionSimulationContextResult]
    caveat: str


class AISystemGovernancePolicyResolutionSimulationReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: str | None = None
    status: str = Field(pattern=POLICY_RESOLUTION_SIM_REPORT_STATUS_PATTERN)
    requested_by_user_id: UUID | None = None
    input_contexts_json: dict | list
    result_json: dict | list
    context_count: int
    blocked_contexts_count: int
    warning_contexts_count: int
    no_policy_contexts_count: int
    created_at: datetime


class AISystemGovernancePolicyResolutionSimulationReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyResolutionSimulationSummary(BaseModel):
    total_reports: int
    active_reports: int
    archived_reports: int
    total_contexts_simulated: int
    blocked_contexts_total: int
    warning_contexts_total: int
    no_policy_contexts_total: int
    latest_report_at: datetime | None = None


class AISystemGovernancePolicyResolutionSimulationDiffRequest(BaseModel):
    base_report_id: UUID
    compare_report_id: UUID
    title: str | None = Field(default=None, max_length=255)
    persist_diff: bool = False
    context_match_strategy: str = Field(
        default="context_key_then_index",
        pattern=POLICY_RESOLUTION_SIM_DIFF_MATCH_STRATEGY_PATTERN,
    )


class AISystemGovernancePolicyResolutionSimulationDiffResponse(BaseModel):
    persisted: bool
    diff_report_id: UUID | None = None
    base_report_id: UUID
    compare_report_id: UUID
    context_match_strategy: str
    added_contexts_count: int
    removed_contexts_count: int
    changed_contexts_count: int
    unchanged_contexts_count: int
    blocked_delta: int
    warning_delta: int
    no_policy_delta: int
    policy_changed_count: int
    guardrail_changed_count: int
    precedence_trace_changed_count: int
    reason_code_summary: dict[str, int]
    reason_code_count: int
    context_diffs: list[dict]
    caveat: str


class AISystemGovernancePolicyResolutionSimulationDiffReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    base_report_id: UUID
    compare_report_id: UUID
    title: str | None = None
    status: str = Field(pattern=POLICY_RESOLUTION_SIM_DIFF_REPORT_STATUS_PATTERN)
    diff_json: dict | list
    context_match_strategy: str
    added_contexts_count: int
    removed_contexts_count: int
    changed_contexts_count: int
    unchanged_contexts_count: int
    blocked_delta: int
    warning_delta: int
    no_policy_delta: int
    reason_code_summary_json: dict | list | None = None
    reason_code_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePolicyResolutionSimulationDiffReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyResolutionSimulationDiffSummary(BaseModel):
    total_diff_reports: int
    active_diff_reports: int
    archived_diff_reports: int
    total_changed_contexts: int
    total_added_contexts: int
    total_removed_contexts: int
    total_policy_changed_contexts: int
    total_guardrail_changed_contexts: int
    total_reason_code_occurrences: int
    top_reason_codes: list[dict]
    latest_diff_report_at: datetime | None = None


class AISystemGovernancePolicyResolutionDiffReasonCodeCatalogItem(BaseModel):
    code: str
    category: str
    description: str
    severity_hint: str


class AISystemGovernancePolicyResolutionDiffReasonCodeCatalogResponse(BaseModel):
    reason_codes: list[AISystemGovernancePolicyResolutionDiffReasonCodeCatalogItem]
    caveat: str


class AISystemGovernancePolicyDiffGatingProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    default_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required_threshold: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    reason_code_rules_json: dict = Field(default_factory=dict)
    status: str = Field(default="active", pattern=POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN)


class AISystemGovernancePolicyDiffGatingProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    default_severity: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required_threshold: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    reason_code_rules_json: dict | None = None
    status: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN)


class AISystemGovernancePolicyDiffGatingProfileArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyDiffGatingProfileRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    status: str = Field(pattern=POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN)
    default_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required_threshold: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    reason_code_rules_json: dict | list
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePolicyDiffGatingClassifyRequest(BaseModel):
    gating_profile_id: UUID
    persist_report: bool = False


class AISystemGovernancePolicyDiffGatingClassifyResponse(BaseModel):
    persisted: bool
    gating_report_id: UUID | None = None
    diff_report_id: UUID
    gating_profile_id: UUID
    max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required: bool
    reason_code_count: int
    severity_summary: dict[str, int]
    reason_code_classifications: list[dict]
    caveat: str


class AISystemGovernancePolicyDiffGatingReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    diff_report_id: UUID
    gating_profile_id: UUID
    status: str = Field(pattern=POLICY_DIFF_GATING_REPORT_STATUS_PATTERN)
    result_json: dict | list
    max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required: bool
    reason_code_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePolicyDiffGatingReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyDiffGatingSummary(BaseModel):
    active_profiles: int
    inactive_profiles: int
    archived_profiles: int
    total_gating_reports: int
    active_gating_reports: int
    archived_gating_reports: int
    review_required_reports: int
    by_max_severity: dict[str, int]
    latest_gating_report_at: datetime | None = None
    caveat: str


class AISystemGovernancePolicyDiffGatingCompareRequest(BaseModel):
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    title: str | None = Field(default=None, max_length=255)
    persist_compare: bool = False


class AISystemGovernancePolicyDiffGatingCompareResponse(BaseModel):
    persisted: bool
    compare_report_id: UUID | None = None
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    base_max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    compare_max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    severity_direction: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_SEVERITY_DIRECTION_PATTERN)
    base_review_required: bool
    compare_review_required: bool
    review_required_changed: bool
    reason_code_changes_count: int
    reason_code_changes: list[dict]
    aggregate_deltas: dict
    caveat: str


class AISystemGovernancePolicyDiffGatingCompareReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    title: str | None = None
    status: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_REPORT_STATUS_PATTERN)
    result_json: dict | list
    base_max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    compare_max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    severity_direction: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_SEVERITY_DIRECTION_PATTERN)
    review_required_changed: bool
    base_review_required: bool
    compare_review_required: bool
    reason_code_changes_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePolicyDiffGatingCompareReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyDiffGatingCompareSummary(BaseModel):
    total_compare_reports: int
    active_compare_reports: int
    archived_compare_reports: int
    severity_increased_reports: int
    severity_decreased_reports: int
    severity_unchanged_reports: int
    review_required_changed_reports: int
    total_reason_code_changes: int
    latest_compare_report_at: datetime | None = None
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    baseline_gating_report_id: UUID | None = None
    baseline_gating_profile_id: UUID | None = None
    watched_reason_codes_json: list[str] | None = None
    ignored_reason_codes_json: list[str] | None = None
    interpretation_rules_json: dict | None = None
    default_interpretation_band: str = Field(default="stable", pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    status: str = Field(default="active", pattern=POLICY_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN)


class AISystemGovernancePolicyDiffGatingComparePresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    baseline_gating_report_id: UUID | None = None
    baseline_gating_profile_id: UUID | None = None
    watched_reason_codes_json: list[str] | None = None
    ignored_reason_codes_json: list[str] | None = None
    interpretation_rules_json: dict | None = None
    default_interpretation_band: str | None = Field(
        default=None,
        pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN,
    )
    version_selection_mode: str | None = Field(
        default=None,
        pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN,
    )
    allow_explicit_version_override: bool | None = None
    status: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN)


class AISystemGovernancePolicyDiffGatingComparePresetArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyDiffGatingComparePresetRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    status: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN)
    baseline_gating_report_id: UUID | None = None
    baseline_gating_profile_id: UUID | None = None
    watched_reason_codes_json: dict | list | None = None
    ignored_reason_codes_json: dict | list | None = None
    interpretation_rules_json: dict | list | None = None
    default_interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    active_version_id: UUID | None = None
    pinned_version_id: UUID | None = None
    version_selection_mode: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN)
    allow_explicit_version_override: bool
    pinned_at: datetime | None = None
    pinned_by_user_id: UUID | None = None
    pin_reason: str | None = None
    unpinned_at: datetime | None = None
    unpinned_by_user_id: UUID | None = None
    unpin_reason: str | None = None
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePolicyDiffGatingComparePresetVersionCreate(BaseModel):
    change_reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernancePolicyDiffGatingComparePresetVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    preset_id: UUID
    version_number: int
    status: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_STATUS_PATTERN)
    snapshot_json: dict
    change_reason: str
    created_by_user_id: UUID | None = None
    activated_by_user_id: UUID | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetVersionActivateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernancePolicyDiffGatingComparePresetVersionArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyDiffGatingComparePresetEvaluateRequest(BaseModel):
    base_gating_report_id: UUID | None = None
    compare_gating_report_id: UUID
    preset_version_id: UUID | None = None
    version_override_reason: str | None = None
    persist_report: bool = False
    persist_compare_report: bool = False


class AISystemGovernancePolicyDiffGatingComparePresetEvaluateResponse(BaseModel):
    persisted: bool
    preset_report_id: UUID | None = None
    preset_id: UUID
    preset_version_id: UUID | None = None
    preset_version_number: int | None = None
    version_resolution_source: str
    pinned_version_id: UUID | None = None
    explicit_version_override_used: bool
    version_override_reason: str | None = None
    preset_snapshot_used: dict
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    compare_report_id: UUID | None = None
    interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    review_required: bool
    watched_reason_codes_hit_count: int
    ignored_reason_codes_hit_count: int
    matched_rules: list[str]
    compare_result: dict
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    preset_id: UUID
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    compare_report_id: UUID | None = None
    preset_version_id: UUID | None = None
    preset_version_number: int | None = None
    preset_snapshot_json: dict | list | None = None
    status: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_REPORT_STATUS_PATTERN)
    result_json: dict | list
    interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    review_required: bool
    watched_reason_codes_hit_count: int
    ignored_reason_codes_hit_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePolicyDiffGatingComparePresetReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePolicyDiffGatingComparePresetPinVersionRequest(BaseModel):
    version_id: UUID
    version_selection_mode: str = Field(
        default="pinned_preferred",
        pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN,
    )
    allow_explicit_version_override: bool = True
    reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernancePolicyDiffGatingComparePresetUnpinVersionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernancePolicyDiffGatingComparePresetPinningStatus(BaseModel):
    preset_id: UUID
    pinned_version_id: UUID | None = None
    pinned_version_number: int | None = None
    version_selection_mode: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN)
    allow_explicit_version_override: bool
    pinned_at: datetime | None = None
    pinned_by_user_id: UUID | None = None
    pin_reason: str | None = None
    unpinned_at: datetime | None = None
    unpinned_by_user_id: UUID | None = None
    unpin_reason: str | None = None
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentCreate(BaseModel):
    preset_id: UUID
    scope_type: str = Field(pattern=GUARDRAIL_POLICY_ASSIGNMENT_SCOPE_PATTERN)
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int = Field(default=100, ge=0)
    reason: str = Field(min_length=1, max_length=5000)
    status: str = Field(default="active", pattern=GUARDRAIL_POLICY_ASSIGNMENT_STATUS_PATTERN)


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentUpdate(BaseModel):
    preset_id: UUID | None = None
    scope_type: str | None = Field(default=None, pattern=GUARDRAIL_POLICY_ASSIGNMENT_SCOPE_PATTERN)
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, min_length=1, max_length=5000)
    status: str | None = Field(default=None, pattern=GUARDRAIL_POLICY_ASSIGNMENT_STATUS_PATTERN)


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead(UUIDTimestampSchema):
    organization_id: UUID
    preset_id: UUID
    scope_type: str
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int
    status: str
    reason: str
    assigned_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistoryRead(BaseModel):
    id: UUID
    organization_id: UUID
    assignment_id: UUID
    event_type: str
    before_json: dict | list | None = None
    after_json: dict | list | None = None
    reason: str
    changed_by_user_id: UUID | None = None
    created_at: datetime


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveRequest(BaseModel):
    explicit_preset_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveResponse(BaseModel):
    resolved_preset_id: UUID | None = None
    resolution_source: str
    assignment_id: UUID | None = None
    precedence_trace: list[dict]
    pinned_version_id: UUID | None = None
    version_selection_mode: str | None = Field(
        default=None,
        pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN,
    )
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultRequest(BaseModel):
    explicit_preset_id: UUID | None = None
    base_gating_report_id: UUID | None = None
    compare_gating_report_id: UUID
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None
    preset_version_id: UUID | None = None
    version_override_reason: str | None = None
    persist_report: bool = False
    persist_compare_report: bool = False


class AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultResponse(
    AISystemGovernancePolicyDiffGatingComparePresetEvaluateResponse
):
    preset_resolution: dict


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentSummary(BaseModel):
    active_assignments: int
    inactive_assignments: int
    archived_assignments: int
    by_scope_type: dict[str, int]
    assignments_to_archived_presets: int
    assignments_to_inactive_presets: int
    highest_priority: int
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsContext(BaseModel):
    context_key: str | None = None
    explicit_preset_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    persist_report: bool = False
    contexts: list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsContext] = Field(
        min_length=1,
        max_length=500,
    )
    include_inactive_assignments: bool = True
    include_archived_assignments: bool = True
    include_preset_version_diagnostics: bool = True


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsContextResult(BaseModel):
    context_key: str | None = None
    context_index: int
    resolution_source: str
    resolved_preset_id: UUID | None = None
    resolved_assignment_id: UUID | None = None
    precedence_trace: list[dict]
    diagnostics: list[dict]
    severity: str
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse(BaseModel):
    persisted: bool = False
    report_id: UUID | None = None
    context_count: int
    resolved_contexts_count: int
    unresolved_contexts_count: int
    warning_contexts_count: int
    critical_contexts_count: int
    contexts: list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsContextResult]
    aggregate_diagnostics: dict[str, int]
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentHealthDiagnosticsResponse(BaseModel):
    active_assignments: int
    inactive_assignments: int
    archived_assignments: int
    assignments_to_inactive_presets: int
    assignments_to_archived_presets: int
    assignments_with_missing_preset: int
    assignments_with_pinned_required_without_pin: int
    duplicate_active_exact_scope_groups: int
    same_scope_conflict_groups: int
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageSummaryResponse(BaseModel):
    total_active_assignments: int
    total_inactive_assignments: int
    total_archived_assignments: int
    total_problem_assignments: int
    assignments_by_scope_type: dict[str, int]
    presets_referenced_by_assignments: int
    active_presets_without_assignments: int
    pinned_presets_with_assignment_count: int
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str | None = None
    description: str | None = None
    status: str
    input_contexts_json: dict | list
    result_json: dict | list
    context_count: int
    resolved_contexts_count: int
    unresolved_contexts_count: int
    warning_contexts_count: int
    critical_contexts_count: int
    aggregate_diagnostics_json: dict | list | None = None
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePresetAssignmentDiagnosticReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePresetAssignmentDiagnosticDiffRequest(BaseModel):
    base_report_id: UUID
    compare_report_id: UUID
    title: str | None = Field(default=None, max_length=255)
    persist_diff: bool = False
    context_match_strategy: str = Field(default="context_key_then_index", pattern="^(context_key_then_index|context_key_only)$")


class AISystemGovernancePresetAssignmentDiagnosticDiffResponse(BaseModel):
    persisted: bool = False
    diff_report_id: UUID | None = None
    base_report_id: UUID
    compare_report_id: UUID
    context_match_strategy: str
    added_contexts_count: int
    removed_contexts_count: int
    changed_contexts_count: int
    unchanged_contexts_count: int
    resolved_delta: int
    unresolved_delta: int
    warning_delta: int
    critical_delta: int
    diagnostic_code_changes_count: int
    context_diffs: list[dict]
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticDiffReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    base_report_id: UUID
    compare_report_id: UUID
    title: str | None = None
    status: str
    diff_json: dict | list
    added_contexts_count: int
    removed_contexts_count: int
    changed_contexts_count: int
    unchanged_contexts_count: int
    resolved_delta: int
    unresolved_delta: int
    warning_delta: int
    critical_delta: int
    diagnostic_code_changes_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePresetAssignmentDiagnosticDiffReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePresetAssignmentDiagnosticReportSummaryResponse(BaseModel):
    total_reports: int
    active_reports: int
    archived_reports: int
    total_diff_reports: int
    active_diff_reports: int
    archived_diff_reports: int
    unresolved_contexts_total: int
    warning_contexts_total: int
    critical_contexts_total: int
    diagnostic_code_changes_total: int
    latest_report_at: datetime | None = None
    latest_diff_report_at: datetime | None = None
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticExportRead(BaseModel):
    id: UUID
    organization_id: UUID
    export_type: str
    source_report_id: UUID | None = None
    source_diff_report_id: UUID | None = None
    status: str
    export_payload_json: dict | list
    canonical_payload_sha256: str
    signature_algorithm: str
    internal_signature: str
    signing_key_id: str | None = None
    exported_by_user_id: UUID | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse(BaseModel):
    export_id: UUID
    export_type: str
    source_report_id: UUID | None = None
    source_diff_report_id: UUID | None = None
    canonical_payload_sha256: str
    signature_algorithm: str
    internal_signature: str
    signing_key_id: str | None = None
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticExportVerifyResponse(BaseModel):
    valid_hash: bool
    valid_signature: bool
    trusted: bool
    canonical_payload_sha256: str
    recomputed_sha256: str
    signature_algorithm: str
    signing_key_id: str | None = None
    status: str
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticExportRevokeRequest(BaseModel):
    reason: str


class AISystemGovernancePresetAssignmentDiagnosticExportSummaryResponse(BaseModel):
    total_exports: int
    generated_exports: int
    revoked_exports: int
    diagnostic_report_exports: int
    diagnostic_diff_report_exports: int
    latest_export_at: datetime | None = None
    latest_revocation_at: datetime | None = None
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticExportDiffRequest(BaseModel):
    base_export_id: UUID
    compare_export_id: UUID
    title: str | None = Field(default=None, max_length=255)
    persist_diff: bool = False


class AISystemGovernancePresetAssignmentDiagnosticExportDiffResponse(BaseModel):
    persisted: bool = False
    export_diff_report_id: UUID | None = None
    base_export_id: UUID
    compare_export_id: UUID
    export_type: str
    payload_hash_changed: bool
    base_verification: dict
    compare_verification: dict
    added_paths_count: int
    removed_paths_count: int
    changed_paths_count: int
    unchanged_paths_count: int
    path_diffs: list[dict]
    reason_code_summary: dict[str, int]
    reason_code_count: int
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    base_export_id: UUID
    compare_export_id: UUID
    export_type: str
    title: str | None = None
    status: str
    diff_json: dict | list
    base_canonical_payload_sha256: str
    compare_canonical_payload_sha256: str
    payload_hash_changed: bool
    base_valid_signature: bool
    compare_valid_signature: bool
    base_trusted: bool
    compare_trusted: bool
    added_paths_count: int
    removed_paths_count: int
    changed_paths_count: int
    unchanged_paths_count: int
    reason_code_summary_json: dict | list | None = None
    reason_code_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernancePresetAssignmentDiagnosticExportDiffReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernancePresetAssignmentDiagnosticExportDiffSummaryResponse(BaseModel):
    total_export_diff_reports: int
    active_export_diff_reports: int
    archived_export_diff_reports: int
    payload_hash_changed_reports: int
    total_added_paths: int
    total_removed_paths: int
    total_changed_paths: int
    untrusted_source_export_comparisons: int
    total_reason_code_occurrences: int
    top_reason_codes: list[dict]
    latest_export_diff_report_at: datetime | None = None
    caveat: str


class AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogItem(BaseModel):
    code: str
    category: str
    description: str
    severity_hint: str


class AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogResponse(BaseModel):
    reason_codes: list[AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogItem]
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    default_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required_threshold: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    reason_code_rules_json: dict = Field(default_factory=dict)
    status: str = Field(default="active", pattern=POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN)


class AISystemGovernanceDiagnosticExportDiffGatingProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    default_severity: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required_threshold: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    reason_code_rules_json: dict | None = None
    status: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN)


class AISystemGovernanceDiagnosticExportDiffGatingProfileArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingProfileRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    status: str = Field(pattern=POLICY_DIFF_GATING_PROFILE_STATUS_PATTERN)
    default_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required_threshold: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    reason_code_rules_json: dict | list
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernanceDiagnosticExportDiffGatingClassifyRequest(BaseModel):
    gating_profile_id: UUID
    persist_report: bool = False


class AISystemGovernanceDiagnosticExportDiffGatingClassifyResponse(BaseModel):
    persisted: bool
    gating_report_id: UUID | None = None
    export_diff_report_id: UUID
    gating_profile_id: UUID
    max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required: bool
    reason_code_count: int
    severity_summary: dict[str, int]
    reason_code_classifications: list[dict]
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    export_diff_report_id: UUID
    gating_profile_id: UUID
    status: str = Field(pattern=POLICY_DIFF_GATING_REPORT_STATUS_PATTERN)
    result_json: dict | list
    max_severity: str = Field(pattern=POLICY_DIFF_GATING_SEVERITY_PATTERN)
    review_required: bool
    reason_code_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernanceDiagnosticExportDiffGatingReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingSummary(BaseModel):
    active_profiles: int
    inactive_profiles: int
    archived_profiles: int
    total_gating_reports: int
    active_gating_reports: int
    archived_gating_reports: int
    review_required_reports: int
    by_max_severity: dict[str, int]
    latest_gating_report_at: datetime | None = None
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingCompareRequest(BaseModel):
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    persist_compare: bool = False
    title: str | None = Field(default=None, max_length=255)


class AISystemGovernanceDiagnosticExportDiffGatingCompareResponse(BaseModel):
    persisted: bool
    compare_report_id: UUID | None = None
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    max_severity_drift: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_MAX_SEVERITY_DRIFT_PATTERN)
    review_required_drift: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_REVIEW_REQUIRED_DRIFT_PATTERN)
    reason_code_changes_count: int
    severity_changes_count: int
    added_reason_codes: list[str]
    removed_reason_codes: list[str]
    changed_reason_codes: list[dict]
    aggregate_delta: dict
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    base_gating_report_id: UUID
    compare_gating_report_id: UUID
    title: str | None = None
    status: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_REPORT_STATUS_PATTERN)
    result_json: dict | list
    max_severity_drift: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_MAX_SEVERITY_DRIFT_PATTERN)
    review_required_drift: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_REVIEW_REQUIRED_DRIFT_PATTERN)
    reason_code_changes_count: int
    severity_changes_count: int
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernanceDiagnosticExportDiffGatingCompareReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingCompareSummary(BaseModel):
    total_compare_reports: int
    active_compare_reports: int
    archived_compare_reports: int
    severity_increased_reports: int
    severity_decreased_reports: int
    severity_unchanged_reports: int
    review_required_became_required_reports: int
    review_required_became_not_required_reports: int
    review_required_unchanged_reports: int
    total_reason_code_changes: int
    total_severity_changes: int
    latest_compare_report_at: datetime | None = None
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    watched_reason_codes_json: list[str] | None = None
    ignored_reason_codes_json: list[str] | None = None
    interpretation_rules_json: dict = Field(default_factory=dict)
    default_interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    status: str = Field(default="active", pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    watched_reason_codes_json: list[str] | None = None
    ignored_reason_codes_json: list[str] | None = None
    interpretation_rules_json: dict | None = None
    default_interpretation_band: str | None = Field(default=None, pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    version_selection_mode: str | None = Field(
        default=None,
        pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN,
    )
    allow_explicit_version_override: bool | None = None
    status: str | None = Field(default=None, pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    status: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_STATUS_PATTERN)
    watched_reason_codes_json: dict | list | None = None
    ignored_reason_codes_json: dict | list | None = None
    interpretation_rules_json: dict | list
    default_interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    active_version_id: UUID | None = None
    pinned_version_id: UUID | None = None
    version_selection_mode: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN)
    allow_explicit_version_override: bool
    pinned_at: datetime | None = None
    pinned_by_user_id: UUID | None = None
    pin_reason: str | None = None
    unpinned_at: datetime | None = None
    unpinned_by_user_id: UUID | None = None
    unpin_reason: str | None = None
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionCreate(BaseModel):
    change_reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    preset_id: UUID
    version_number: int
    status: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_STATUS_PATTERN)
    snapshot_json: dict
    change_reason: str
    created_by_user_id: UUID | None = None
    activated_by_user_id: UUID | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionActivateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinVersionRequest(BaseModel):
    version_id: UUID
    version_selection_mode: str = Field(
        default="pinned_preferred",
        pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN,
    )
    allow_explicit_version_override: bool = True
    reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetUnpinVersionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinningStatus(BaseModel):
    preset_id: UUID
    active_version_id: UUID | None = None
    active_version_number: int | None = None
    pinned_version_id: UUID | None = None
    pinned_version_number: int | None = None
    version_selection_mode: str = Field(pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN)
    allow_explicit_version_override: bool
    pinned_at: datetime | None = None
    pinned_by_user_id: UUID | None = None
    pin_reason: str | None = None
    unpinned_at: datetime | None = None
    unpinned_by_user_id: UUID | None = None
    unpin_reason: str | None = None
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateRequest(BaseModel):
    preset_id: UUID
    preset_version_id: UUID | None = None
    version_override_reason: str | None = None
    persist_report: bool = False


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateResponse(BaseModel):
    persisted: bool
    preset_report_id: UUID | None = None
    compare_report_id: UUID
    preset_id: UUID
    preset_version_id: UUID | None = None
    preset_version_number: int | None = None
    preset_snapshot_used: dict
    version_resolution_source: str
    pinned_version_id: UUID | None = None
    explicit_version_override_used: bool
    version_override_reason: str | None = None
    interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    review_required: bool
    matched_rules: list[dict]
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    compare_report_id: UUID
    preset_id: UUID
    preset_version_id: UUID | None = None
    preset_version_number: int | None = None
    preset_snapshot_json: dict | list | None = None
    version_resolution_source: str | None = None
    pinned_version_id: UUID | None = None
    explicit_version_override_used: bool
    version_override_reason: str | None = None
    status: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_REPORT_STATUS_PATTERN)
    result_json: dict | list
    interpretation_band: str = Field(pattern=POLICY_DIFF_GATING_INTERPRETATION_BAND_PATTERN)
    review_required: bool
    matched_rules_json: dict | list | None = None
    created_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportArchiveRequest(BaseModel):
    reason: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetSummary(BaseModel):
    active_presets: int
    inactive_presets: int
    archived_presets: int
    total_preset_versions: int
    active_preset_versions: int
    draft_preset_versions: int
    deprecated_preset_versions: int
    archived_preset_versions: int
    presets_without_active_version: int
    pinned_presets: int
    pinned_required_presets: int
    pinned_preferred_presets: int
    presets_allowing_explicit_override: int
    presets_blocking_explicit_override: int
    total_preset_reports: int
    active_preset_reports: int
    archived_preset_reports: int
    by_interpretation_band: dict[str, int]
    review_required_reports: int
    latest_preset_report_at: datetime | None = None
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCreate(BaseModel):
    preset_id: UUID
    scope_type: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PATTERN)
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int = Field(default=100, ge=0)
    reason: str = Field(min_length=1, max_length=5000)
    status: str = Field(default="active", pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_STATUS_PATTERN)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentUpdate(BaseModel):
    preset_id: UUID | None = None
    scope_type: str | None = Field(default=None, pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PATTERN)
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, min_length=1, max_length=5000)
    status: str | None = Field(default=None, pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_STATUS_PATTERN)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead(UUIDTimestampSchema):
    organization_id: UUID
    preset_id: UUID
    scope_type: str
    scope_id: UUID | None = None
    scope_json: dict | list | None = None
    priority: int
    status: str
    reason: str
    assigned_by_user_id: UUID | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistoryRead(BaseModel):
    id: UUID
    organization_id: UUID
    assignment_id: UUID
    event_type: str = Field(pattern=DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_EVENT_PATTERN)
    before_json: dict | list | None = None
    after_json: dict | list | None = None
    reason: str
    changed_by_user_id: UUID | None = None
    created_at: datetime


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveRequest(BaseModel):
    explicit_preset_id: UUID | None = None
    compare_report_id: UUID | None = None
    gating_profile_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None
    export_type: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveResponse(BaseModel):
    resolved_preset_id: UUID | None = None
    resolution_source: str
    assignment_id: UUID | None = None
    precedence_trace: list[dict]
    active_version_id: UUID | None = None
    pinned_version_id: UUID | None = None
    version_selection_mode: str | None = Field(
        default=None,
        pattern=POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODE_PATTERN,
    )
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultRequest(BaseModel):
    explicit_preset_id: UUID | None = None
    gating_profile_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None
    export_type: str | None = None
    preset_version_id: UUID | None = None
    version_override_reason: str | None = None
    persist_report: bool = False


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultResponse(
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateResponse
):
    preset_resolution: dict


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentSummary(BaseModel):
    active_assignments: int
    inactive_assignments: int
    archived_assignments: int
    by_scope_type: dict[str, int]
    assignments_to_archived_presets: int
    assignments_to_inactive_presets: int
    highest_priority: int
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsContext(BaseModel):
    context_key: str | None = None
    explicit_preset_id: UUID | None = None
    compare_report_id: UUID | None = None
    gating_profile_id: UUID | None = None
    sequence_pack_id: UUID | None = None
    ai_system_ids: list[UUID] | None = None
    review_types: list[str] | None = None
    rollout_class: str | None = None
    export_type: str | None = None


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsRequest(BaseModel):
    contexts: list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsContext] = Field(
        min_length=1,
        max_length=500,
    )
    include_inactive_assignments: bool = True
    include_archived_assignments: bool = True
    include_version_diagnostics: bool = True


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsContextResult(BaseModel):
    context_key: str | None = None
    context_index: int
    resolution_source: str
    resolved_preset_id: UUID | None = None
    resolved_assignment_id: UUID | None = None
    precedence_trace: list[dict]
    diagnostics: list[dict]
    severity: str
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse(BaseModel):
    context_count: int
    resolved_contexts_count: int
    unresolved_contexts_count: int
    warning_contexts_count: int
    critical_contexts_count: int
    contexts: list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsContextResult]
    aggregate_diagnostics: dict[str, int]
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHealthDiagnosticsResponse(BaseModel):
    active_assignments: int
    inactive_assignments: int
    archived_assignments: int
    assignments_to_inactive_presets: int
    assignments_to_archived_presets: int
    assignments_with_missing_preset: int
    assignments_with_pinned_required_without_pin: int
    duplicate_active_exact_scope_groups: int
    same_scope_conflict_groups: int
    caveat: str


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageSummaryResponse(BaseModel):
    total_active_assignments: int
    total_inactive_assignments: int
    total_archived_assignments: int
    total_problem_assignments: int
    assignments_by_scope_type: dict[str, int]
    presets_referenced_by_assignments: int
    active_presets_without_assignments: int
    pinned_presets_with_assignment_count: int
    caveat: str


class AISystemGovernancePolicyDiffGatingComparePresetSummary(BaseModel):
    active_presets: int
    inactive_presets: int
    archived_presets: int
    total_preset_versions: int
    active_preset_versions: int
    draft_preset_versions: int
    deprecated_preset_versions: int
    archived_preset_versions: int
    presets_without_active_version: int
    pinned_presets: int
    pinned_required_presets: int
    pinned_preferred_presets: int
    presets_allowing_explicit_override: int
    presets_blocking_explicit_override: int
    total_preset_reports: int
    active_preset_reports: int
    archived_preset_reports: int
    review_required_reports: int
    by_interpretation_band: dict[str, int]
    latest_preset_report_at: datetime | None = None
    caveat: str


class AISystemGovernancePhase5ContractGroup(BaseModel):
    group_key: str
    title: str
    description: str
    route_prefix: str
    critical_endpoints: list[str]
    response_contract_fields: list[str]
    invariants: dict[str, bool]
    caveats: list[str]


class AISystemGovernancePhase5ContractsResponse(BaseModel):
    phase: str
    status: str
    group_count: int
    groups: list[AISystemGovernancePhase5ContractGroup]
    caveat: str


class AISystemGovernancePhase5CompatibilitySummaryResponse(BaseModel):
    phase: str
    status: str
    protected_groups_count: int
    protected_endpoint_count: int
    contract_testing_strategy: str
    caveat: str


class AISystemGovernancePhase6ContractGroup(BaseModel):
    group_key: str
    title: str
    description: str
    route_prefix: str
    critical_endpoints: list[str]
    response_contract_fields: list[str]
    invariants: dict[str, bool]
    caveats: list[str]


class AISystemGovernancePhase6ContractsResponse(BaseModel):
    phase: str
    status: str
    group_count: int
    groups: list[AISystemGovernancePhase6ContractGroup]
    caveat: str


class AISystemGovernancePhase7ContractGroup(BaseModel):
    group_key: str
    title: str
    description: str
    route_prefix: str
    critical_endpoints: list[str]
    endpoints: list[str]
    response_contract_fields: list[str]
    protected_fields: list[str]
    read_write_semantics: dict[str, Any]
    invariants: dict[str, bool]
    caveats: list[str]
    non_execution_guarantee: str
    no_legal_regulatory_determination: str


class AISystemGovernancePhase7ContractsResponse(BaseModel):
    phase: str
    status: str
    group_count: int
    groups: list[AISystemGovernancePhase7ContractGroup]
    execution_allowed: bool = False
    real_runner_present: bool = False
    job_queue_present: bool = False
    future_runner_requires_architecture_review: bool = True
    caveat: str


class AISystemGovernancePhase8ContractGroup(BaseModel):
    group_key: str
    title: str
    description: str
    route_prefix: str
    critical_endpoints: list[str]
    endpoints: list[str]
    response_contract_fields: list[str]
    protected_fields: list[str]
    read_write_semantics: dict[str, Any]
    invariants: dict[str, bool]
    caveats: list[str]
    non_execution_guarantee: str
    no_legal_regulatory_determination: str


class AISystemGovernancePhase8ContractsResponse(BaseModel):
    phase: str
    status: str
    group_count: int
    groups: list[AISystemGovernancePhase8ContractGroup]
    execution_allowed: bool = False
    real_runner_present: bool = False
    job_queue_present: bool = False
    noop_runner_only: bool = True
    caveat: str
