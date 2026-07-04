from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UUIDTimestampSchema

RISK_APPETITE_SCOPE_PATTERN = "^(org|business_unit)$"
RISK_APPETITE_CATEGORY_PATTERN = "^(operational|financial|compliance|reputational|technology|vendor|ai_governance)$"


class RiskAppetiteThresholdCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: str = Field(pattern=RISK_APPETITE_SCOPE_PATTERN)
    scope_id: UUID | None = None
    risk_category: str = Field(pattern=RISK_APPETITE_CATEGORY_PATTERN)
    max_acceptable_score: int = Field(ge=1, le=25)
    escalation_owner_id: UUID
    notes: str | None = None


class RiskAppetiteThresholdUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_acceptable_score: int | None = Field(default=None, ge=1, le=25)
    escalation_owner_id: UUID | None = None
    notes: str | None = None


class RiskAppetiteThresholdDeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=4000)


class RiskAppetiteThresholdRead(UUIDTimestampSchema):
    organization_id: UUID
    scope_type: str = Field(pattern=RISK_APPETITE_SCOPE_PATTERN)
    scope_id: UUID | None = None
    risk_category: str = Field(pattern=RISK_APPETITE_CATEGORY_PATTERN)
    max_acceptable_score: int
    escalation_owner_id: UUID
    is_active: bool
    notes: str | None = None
    created_by_user_id: UUID


class RiskAppetiteSummary(BaseModel):
    total_thresholds: int
    active_thresholds: int
    by_category: dict[str, int]
    breach_count: int
    categories_without_threshold: list[str]


class RiskAppetiteBreachRiskSummary(BaseModel):
    id: UUID
    name: str
    score: int
    category: str


class RiskAppetiteBreachRead(BaseModel):
    alert_id: UUID
    status: str
    severity: str
    title: str
    threshold_id: UUID | None = None
    scope_type: str | None = None
    scope_id: UUID | None = None
    risk_category: str | None = None
    new_score: int | None = None
    max_acceptable_score: int | None = None
    risk: RiskAppetiteBreachRiskSummary | None = None
    created_at: datetime
