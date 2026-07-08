from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.framework import ApplicabilityQuestionRead


class OrganizationObligationStateRead(BaseModel):
    id: UUID
    organization_id: UUID
    obligation_id: UUID
    applicability_status: str
    implementation_status: str
    owner_user_id: UUID | None = None
    justification: str | None = None
    created_at: datetime
    updated_at: datetime


class ObligationContentVersionRead(BaseModel):
    id: UUID
    obligation_id: UUID
    version_label: str
    obligation_text: str
    normalized_summary: str | None = None
    source_reference: str | None = None
    source_url: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    coverage_level: str
    review_status: str
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    superseded_by_version_id: UUID | None = None
    metadata_json: dict | None = None
    created_at: datetime


class ObligationContentVersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=64)
    obligation_text: str = Field(min_length=1)
    normalized_summary: str | None = None
    source_reference: str | None = None
    source_url: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    coverage_level: str = Field(default="starter", pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")
    review_status: str = Field(default="unreviewed", pattern="^(unreviewed|internal_review|expert_reviewed|customer_verified|superseded)$")
    metadata_json: dict | None = None


class ObligationEvidenceRequirementRead(BaseModel):
    id: UUID
    framework_id: UUID
    obligation_id: UUID
    requirement_key: str
    title: str
    description: str | None = None
    evidence_type: str
    required: bool
    frequency: str | None = None
    status: str
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ObligationEvidenceRequirementCreate(BaseModel):
    requirement_key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    evidence_type: str = Field(
        pattern="^(policy_document|screenshot|system_export|attestation|audit_report|risk_assessment|meeting_record|configuration_snapshot|training_record|vendor_document|ai_model_documentation|other)$"
    )
    required: bool = False
    frequency: str | None = None
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")
    metadata_json: dict | None = None


class ObligationControlSuggestionRead(BaseModel):
    id: UUID
    framework_id: UUID
    obligation_id: UUID
    control_title: str
    control_description: str | None = None
    control_domain: str | None = None
    control_type: str | None = None
    priority: str
    status: str
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ObligationControlSuggestionCreate(BaseModel):
    control_title: str = Field(min_length=1, max_length=255)
    control_description: str | None = None
    control_domain: str | None = None
    control_type: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")
    metadata_json: dict | None = None


class ObligationRead(BaseModel):
    id: UUID
    framework_id: UUID
    framework_section_id: UUID | None = None
    reference_code: str
    title: str
    description: str | None = None
    plain_language_summary: str | None = None
    obligation_type: str | None = None
    jurisdiction: str
    source_url: str | None = None
    version: str | None = None
    ig_level: str | None = None
    status: str
    effective_date: date | None = None
    parent_obligation_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    organization_state: OrganizationObligationStateRead | None = None
    framework: dict | None = None
    section: dict | None = None
    current_content_version: ObligationContentVersionRead | None = None
    coverage_level: str | None = None
    review_status: str | None = None
    evidence_requirements: list[ObligationEvidenceRequirementRead] = []
    control_suggestions: list[ObligationControlSuggestionRead] = []
    applicability_questions: list[ApplicabilityQuestionRead] = []
    latest_suggested_applicability: str | None = None
    latest_suggestion_stale_inputs: int = 0
    suggestion_conflicts_with_org_state: bool = False
    linked_controls_count: int = 0
    context_flags: list[str] = []


class ObligationStateUpdateRequest(BaseModel):
    applicability_status: str = Field(pattern="^(pending|applicable|not_applicable|needs_review)$")
    implementation_status: str = Field(pattern="^(not_started|in_progress|implemented|blocked)$")
    owner_user_id: UUID | None = None
    justification: str | None = None
