from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FrameworkRead(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    category: str
    jurisdiction: str
    authority: str | None = None
    version: str | None = None
    status: str
    coverage_level: str
    source_url: str | None = None
    effective_date: date | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkDetail(FrameworkRead):
    obligation_count: int
    active_obligation_count: int


class FrameworkActivationRequest(BaseModel):
    notes: str | None = None


class OrganizationFrameworkRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID
    status: str
    activated_by_user_id: UUID | None = None
    activated_at: datetime | None = None
    deactivated_by_user_id: UUID | None = None
    deactivated_at: datetime | None = None
    notes: str | None = None
    framework: FrameworkRead


class FrameworkVersionRead(BaseModel):
    id: UUID
    framework_id: UUID
    version_label: str
    source_url: str | None = None
    source_reference: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    status: str
    coverage_level: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkVersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=64)
    source_url: str | None = None
    source_reference: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    status: str = Field(default="active", pattern="^(draft|active|superseded|archived)$")
    coverage_level: str = Field(default="starter", pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")
    notes: str | None = None


class FrameworkSectionRead(BaseModel):
    id: UUID
    framework_id: UUID
    framework_version_id: UUID | None = None
    parent_section_id: UUID | None = None
    section_code: str
    title: str
    description: str | None = None
    sort_order: int
    status: str
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class FrameworkSectionCreate(BaseModel):
    framework_version_id: UUID | None = None
    parent_section_id: UUID | None = None
    section_code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sort_order: int = 0
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")
    metadata_json: dict | None = None


class ApplicabilityQuestionCreate(BaseModel):
    obligation_id: UUID | None = None
    question_key: str = Field(min_length=1, max_length=128)
    question_text: str = Field(min_length=1)
    help_text: str | None = None
    answer_type: str = Field(pattern="^(boolean|single_select|multi_select|text|number|date)$")
    required: bool = False
    sort_order: int = 0
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")
    metadata_json: dict | None = None


class ApplicabilityQuestionRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    framework_id: UUID
    obligation_id: UUID | None = None
    question_key: str
    question_text: str
    help_text: str | None = None
    answer_type: str
    required: bool
    sort_order: int
    status: str
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ContentImportRequest(BaseModel):
    import_type: str = Field(min_length=1, max_length=64)
    coverage_level: str = Field(default="starter", pattern="^(metadata_only|starter|partial|reviewed|full_verified)$")
    source_name: str | None = None
    source_reference: str | None = None
    payload_json: dict


class ContentImportPreviewResponse(BaseModel):
    valid: bool
    counts: dict
    validation_errors: list[str]


class FrameworkContentSummary(BaseModel):
    framework_id: UUID
    active_version: str | None = None
    coverage_level: str
    total_sections: int
    total_obligations: int
    obligations_with_content_versions: int
    obligations_with_evidence_requirements: int
    obligations_with_control_suggestions: int
    applicability_questions: int
    reviewed_obligations: int
    unreviewed_obligations: int


class LocalFrameworkPackRead(BaseModel):
    pack_key: str
    framework_code: str
    framework_name: str
    version_label: str
    coverage_level: str
    review_status: str
    caveat: str
    source_reference: str | None = None
    source_url: str | None = None


class FrameworkContentPackApplyRequest(BaseModel):
    dry_run: bool = True
    force_update: bool = False


class FrameworkContentPackValidationResponse(BaseModel):
    valid: bool
    pack_key: str
    framework_code: str | None = None
    framework_name: str | None = None
    coverage_level: str | None = None
    review_status: str | None = None
    caveat: str | None = None
    counts: dict
    validation_errors: list[str]
    warnings: list[str] = []
    persisted: bool = False


class FrameworkCoverageReportRead(BaseModel):
    id: UUID | None = None
    framework_id: UUID
    framework_version_id: UUID | None = None
    pack_key: str
    coverage_level: str
    review_status: str
    total_sections: int
    total_obligations: int
    obligations_with_content: int
    obligations_with_questions: int
    obligations_with_evidence_requirements: int
    obligations_with_control_suggestions: int
    missing_content_count: int
    missing_question_count: int
    missing_evidence_requirement_count: int
    missing_control_suggestion_count: int
    coverage_percent_estimate: float
    report_json: dict
    generated_at: datetime
    created_by_user_id: UUID | None = None
    caveat: str


class FrameworkCoverageReportRequest(BaseModel):
    persist: bool = False


class FrameworkCoverageGapsResponse(BaseModel):
    framework_id: UUID
    obligations_missing_content: list[dict]
    obligations_missing_applicability_questions: list[dict]
    obligations_missing_evidence_requirements: list[dict]
    obligations_missing_control_suggestions: list[dict]
    sections_without_obligations: list[dict]
    obligations_without_sections: list[dict]
    caveat: str


class GlobalFrameworkCoverageItem(BaseModel):
    framework_id: UUID
    framework_code: str
    framework_name: str
    active_version: str | None = None
    coverage_level: str
    review_status: str
    total_sections: int
    total_obligations: int
    coverage_percent_estimate: float
    caveat: str
