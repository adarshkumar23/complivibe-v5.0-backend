from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

MAPPING_STRENGTH_PATTERN = "^(full|partial|compensating)$"
MAPPING_STATUS_PATTERN = "^(active|inactive|under_review)$"
COVERAGE_STATUS_PATTERN = "^(covers|partial|insufficient)$"


class CommonControlMappingCreate(BaseModel):
    control_id: UUID
    framework_id: UUID
    obligation_id: UUID
    section_reference: str | None = Field(default=None, max_length=100)
    mapping_rationale: str | None = None
    mapping_strength: str = Field(default="full", pattern=MAPPING_STRENGTH_PATTERN)
    verified_by_user_id: UUID | None = None


class CommonControlMappingUpdate(BaseModel):
    section_reference: str | None = Field(default=None, max_length=100)
    mapping_rationale: str | None = None
    mapping_strength: str | None = Field(default=None, pattern=MAPPING_STRENGTH_PATTERN)
    status: str | None = Field(default=None, pattern=MAPPING_STATUS_PATTERN)
    verified_by_user_id: UUID | None = None


class CommonControlMappingRead(UUIDTimestampSchema):
    organization_id: UUID
    control_id: UUID
    framework_id: UUID
    obligation_id: UUID
    section_reference: str | None = None
    mapping_rationale: str | None = None
    mapping_strength: str
    verified_by_user_id: UUID | None = None
    verified_at: datetime | None = None
    status: str
    created_by_user_id: UUID


class CommonControlEvidenceCoverageCreate(BaseModel):
    control_id: UUID
    evidence_id: UUID
    mapping_id: UUID
    coverage_status: str = Field(pattern=COVERAGE_STATUS_PATTERN)
    coverage_notes: str | None = None


class CommonControlEvidenceCoverageRead(BaseModel):
    id: UUID
    organization_id: UUID
    control_id: UUID
    evidence_id: UUID
    mapping_id: UUID
    coverage_status: str
    coverage_notes: str | None = None
    assessed_by_user_id: UUID | None = None
    assessed_at: datetime | None = None
    created_at: datetime


class CommonControlCoverageEvidenceItem(BaseModel):
    evidence_id: UUID
    evidence_title: str
    coverage_status: str
    expiry_date: date | None = None


class CommonControlCoverageSummary(BaseModel):
    total_evidence: int
    covering: int
    partial: int
    insufficient: int
    coverage_pct: float


class CommonControlCoverageObligation(BaseModel):
    obligation_id: UUID
    section_reference: str | None = None
    mapping_strength: str
    evidence_coverage: list[CommonControlCoverageEvidenceItem]
    coverage_summary: CommonControlCoverageSummary


class CommonControlCoverageFramework(BaseModel):
    framework_id: UUID
    framework_name: str
    obligations: list[CommonControlCoverageObligation]
    framework_coverage_pct: float


class CommonControlCoverageReport(BaseModel):
    control: dict
    frameworks_covered: list[CommonControlCoverageFramework]
    total_frameworks: int
    total_obligations: int
    overall_coverage_pct: float


class EvidenceReuseItem(BaseModel):
    evidence_id: UUID
    evidence_title: str
    reuse_count: int
    frameworks_covered: list[str]
    obligations_covered: list[str]


class EvidenceReuseReport(BaseModel):
    reused_evidence: list[EvidenceReuseItem]
    total_evidence_items: int
    reused_count: int
    reuse_rate: float


class CommonControlsTopItem(BaseModel):
    control_id: UUID
    control_name: str
    framework_count: int
    obligation_count: int


class CommonControlsSummary(BaseModel):
    total_common_controls: int
    total_mappings: int
    by_mapping_strength: dict[str, int]
    frameworks_with_common_controls: int
    top_common_controls: list[CommonControlsTopItem]
