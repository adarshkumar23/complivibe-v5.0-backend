from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

VIOLATION_TYPE_PATTERN = "^(violation|near_miss|observation|procedural_gap)$"
SEVERITY_IMPACT_PATTERN = "^(low|medium|high|critical)$"


class PolicyIssueLinkCreate(BaseModel):
    policy_id: UUID
    issue_id: UUID
    violation_type: str = Field(default="violation", pattern=VIOLATION_TYPE_PATTERN)
    severity_impact: str = Field(default="medium", pattern=SEVERITY_IMPACT_PATTERN)
    notes: str | None = None


class PolicyIssueLinkUpdate(BaseModel):
    violation_type: str | None = Field(default=None, pattern=VIOLATION_TYPE_PATTERN)
    severity_impact: str | None = Field(default=None, pattern=SEVERITY_IMPACT_PATTERN)
    notes: str | None = None


class PolicyIssuePolicyRef(BaseModel):
    id: UUID
    name: str


class PolicyIssueIssueRef(BaseModel):
    id: UUID
    title: str
    status: str
    severity: str


class PolicyIssueLinkResponse(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    issue_id: UUID
    violation_type: str = Field(pattern=VIOLATION_TYPE_PATTERN)
    severity_impact: str = Field(pattern=SEVERITY_IMPACT_PATTERN)
    notes: str | None = None
    linked_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    policy: PolicyIssuePolicyRef | None = None
    issue: PolicyIssueIssueRef | None = None


class PolicyEffectivenessResponse(BaseModel):
    policy_id: UUID
    total_issues_linked: int
    open_issues: int
    resolved_issues: int
    by_violation_type: dict[str, int]
    by_severity_impact: dict[str, int]
    trend_last_30d: int
    trend_last_90d: int
    effectiveness_score: float


class IssuePolicyContextResponse(BaseModel):
    issue_id: UUID
    total_policies_linked: int
    policies: list[dict]
    most_severe_impact: str | None


class OrgPolicyEffectivenessSummaryResponse(BaseModel):
    total_links: int
    policies_with_issues: int
    policies_without_issues: int
    most_violated_policies: list[dict]
    violation_type_breakdown: dict[str, int]
    open_issues_by_policy: list[dict]
