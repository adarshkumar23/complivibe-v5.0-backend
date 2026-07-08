from pydantic import BaseModel, ConfigDict, Field


class AIGovernanceDashboardRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # `risk_tier` is a free-text, nullable column (not a fixed enum) -- values in
    # practice include internal tiers (critical/high/medium/low) and EU AI Act tiers
    # (unacceptable/high/limited/minimal), plus systems with no tier assigned at all
    # (bucketed as "unassessed" by the service). A fixed-field model here would
    # silently drop any bucket it didn't anticipate via pydantic's default
    # extra-field-ignore behavior -- which is exactly how systems without an explicit
    # tier were previously vanishing from the count. Keep this a free-form mapping so
    # every system is always accounted for, however it's tiered.
    ai_systems_by_tier: dict[str, int]
    governance_coverage_pct: float
    outstanding_reviews_count: int
    policy_violations_count: int
    shadow_ai_detected_count: int
    high_risk_systems_without_approval: int
    monitoring_alerts_by_system: list[dict]
    pillar2_status: str = Field(alias="_pillar2_status")
