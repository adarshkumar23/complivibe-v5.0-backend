from pydantic import BaseModel, ConfigDict, Field


class AIGovernanceSystemsByTier(BaseModel):
    critical: int
    high: int
    medium: int
    low: int


class AIGovernanceDashboardRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ai_systems_by_tier: AIGovernanceSystemsByTier
    governance_coverage_pct: float
    outstanding_reviews_count: int
    policy_violations_count: int
    shadow_ai_detected_count: int
    high_risk_systems_without_approval: int
    monitoring_alerts_by_system: list[dict]
    pillar2_status: str = Field(alias="_pillar2_status")
