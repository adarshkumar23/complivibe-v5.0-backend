from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class RiskControlSummary(BaseModel):
    control_id: UUID
    title: str
    status: str


class RiskEvidenceSummary(BaseModel):
    evidence_item_id: UUID
    title: str
    review_status: str
    freshness_status: str


class RiskControlLinkCreate(BaseModel):
    control_id: UUID
    link_type: str = Field(default="mitigates", pattern="^(mitigates|detects|compensates|related)$")
    rationale: str | None = None


class RiskControlLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    risk_id: UUID
    control_id: UUID
    link_type: str
    status: str
    rationale: str | None = None
    linked_by_user_id: UUID | None = None
    linked_at: datetime | None = None
    unlinked_at: datetime | None = None


class RiskEvidenceLinkCreate(BaseModel):
    evidence_item_id: UUID
    link_type: str = Field(default="related", pattern="^(supports_assessment|supports_acceptance|supports_mitigation|related)$")
    rationale: str | None = None


class RiskEvidenceLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    risk_id: UUID
    evidence_item_id: UUID
    link_type: str
    status: str
    rationale: str | None = None
    linked_by_user_id: UUID | None = None
    linked_at: datetime | None = None
    unlinked_at: datetime | None = None


class RiskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    category: str = Field(default="other")
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    financial_impact: int | None = Field(default=None, ge=1, le=5)
    brand_impact: int | None = Field(default=None, ge=1, le=5)
    operational_impact: int | None = Field(default=None, ge=1, le=5)
    composite_score_method: str = Field(default="standard", pattern="^(standard|factor_based)$")
    treatment_strategy: str = Field(default="undecided", pattern="^(mitigate|accept|transfer|avoid|undecided)$")
    treatment_option: str | None = Field(default=None, pattern="^(avoid|reduce|share|retain)$")
    risk_context_internal: str | None = None
    risk_context_external: str | None = None
    residual_risk_acceptable: bool | None = None
    risk_communication_plan: str | None = None
    owner_user_id: UUID | None = None
    target_date: datetime | None = None
    metadata_json: dict | None = None


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    category: str | None = None
    status: str | None = Field(default=None, pattern="^(identified|assessing|treatment_planned|in_treatment|accepted|mitigated|monitored|archived)$")
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    financial_impact: int | None = Field(default=None, ge=1, le=5)
    brand_impact: int | None = Field(default=None, ge=1, le=5)
    operational_impact: int | None = Field(default=None, ge=1, le=5)
    composite_score_method: str | None = Field(default=None, pattern="^(standard|factor_based)$")
    residual_likelihood: int | None = Field(default=None, ge=1, le=5)
    residual_impact: int | None = Field(default=None, ge=1, le=5)
    treatment_strategy: str | None = Field(default=None, pattern="^(mitigate|accept|transfer|avoid|undecided)$")
    treatment_option: str | None = Field(default=None, pattern="^(avoid|reduce|share|retain)$")
    risk_context_internal: str | None = None
    risk_context_external: str | None = None
    residual_risk_acceptable: bool | None = None
    risk_communication_plan: str | None = None
    owner_user_id: UUID | None = None
    target_date: datetime | None = None
    review_due_at: datetime | None = None
    metadata_json: dict | None = None


class RiskRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    description: str | None = None
    category: str
    status: str
    severity: str
    likelihood: int
    impact: int
    inherent_score: int
    financial_impact: int | None = None
    brand_impact: int | None = None
    operational_impact: int | None = None
    composite_score_method: str = Field(pattern="^(standard|factor_based)$")
    residual_likelihood: int | None = None
    residual_impact: int | None = None
    residual_score: int | None = None
    treatment_strategy: str
    treatment_option: str | None = None
    risk_context_internal: str | None = None
    risk_context_external: str | None = None
    residual_risk_acceptable: bool | None = None
    risk_communication_plan: str | None = None
    owner_user_id: UUID | None = None
    target_date: datetime | None = None
    accepted_by_user_id: UUID | None = None
    accepted_at: datetime | None = None
    acceptance_reason: str | None = None
    review_due_at: datetime | None = None
    metadata_json: dict | None = None
    created_by_user_id: UUID | None = None


class RiskDetail(RiskRead):
    linked_controls: list[RiskControlSummary]
    linked_evidence: list[RiskEvidenceSummary]


class RiskAcceptRequest(BaseModel):
    acceptance_reason: str = Field(min_length=3, max_length=2000)
    review_due_at: datetime | None = None


class RiskSummary(BaseModel):
    total_risks: int
    open_risks: int
    accepted_risks: int
    mitigated_risks: int
    critical_risks: int
    high_risks: int
    medium_risks: int
    low_risks: int
    risks_without_controls: int
    risks_without_owner: int
    overdue_risk_reviews: int


class RiskHeatmapCell(BaseModel):
    likelihood: int
    impact: int
    count: int
    risks: list[dict]


class RiskHeatmap(BaseModel):
    matrix: list[RiskHeatmapCell]


class OrgRiskSettingsRead(BaseModel):
    financial_weight: float
    brand_weight: float
    operational_weight: float


class OrgRiskSettingsUpdate(BaseModel):
    financial_weight: float = Field(ge=0.01, le=0.99)
    brand_weight: float = Field(ge=0.01, le=0.99)
    operational_weight: float = Field(ge=0.01, le=0.99)
