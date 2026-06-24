from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

MITIGATION_STRENGTH_PATTERN = "^(full|partial|indirect)$"


class PolicyRiskMappingCreate(BaseModel):
    policy_id: UUID
    risk_id: UUID
    mitigation_strength: str = Field(default="partial", pattern=MITIGATION_STRENGTH_PATTERN)
    notes: str | None = None


class PolicyRiskMappingUpdate(BaseModel):
    mitigation_strength: str | None = Field(default=None, pattern=MITIGATION_STRENGTH_PATTERN)
    notes: str | None = None


class PolicyRiskPolicyRef(BaseModel):
    id: UUID
    name: str


class PolicyRiskRiskRef(BaseModel):
    id: UUID
    title: str
    severity: str
    status: str


class PolicyRiskMappingResponse(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    risk_id: UUID
    mitigation_strength: str = Field(pattern=MITIGATION_STRENGTH_PATTERN)
    notes: str | None = None
    mapped_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    policy: PolicyRiskPolicyRef | None = None
    risk: PolicyRiskRiskRef | None = None


class PolicyRiskCoverageResponse(BaseModel):
    policy_id: UUID
    total_risks_mapped: int
    by_strength: dict[str, int]
    risk_severity_breakdown: dict[str, int]
    unmapped_risk_count: int


class RiskPolicyCoverageResponse(BaseModel):
    risk_id: UUID
    total_policies_mapped: int
    by_strength: dict[str, int]
    has_full_coverage: bool
    policy_statuses: dict[str, int]


class OrgMappingSummaryResponse(BaseModel):
    total_mappings: int
    policies_with_mappings: int
    policies_without_mappings: int
    risks_with_mappings: int
    risks_without_mappings: int
    coverage_rate: float
    top_covered_risks: list[dict]
    uncovered_risks: list[dict]
