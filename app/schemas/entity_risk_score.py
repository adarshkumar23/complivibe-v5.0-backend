from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ENTITY_TYPE_PATTERN = "^(vendor|asset|business_unit|framework)$"
SCORE_METHOD_PATTERN = "^(equal_weight|max_score|weighted_avg)$"
SCORE_BAND_PATTERN = "^(critical|high|medium|low|none)$"


class EntityRiskScoreComputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(pattern=ENTITY_TYPE_PATTERN)
    entity_id: UUID
    score_method: str = Field(default="equal_weight", pattern=SCORE_METHOD_PATTERN)


class EntityRiskScoreRead(BaseModel):
    id: UUID
    organization_id: UUID
    entity_type: str = Field(pattern=ENTITY_TYPE_PATTERN)
    entity_id: UUID
    entity_label: str
    composite_score: float
    score_band: str = Field(pattern=SCORE_BAND_PATTERN)
    risk_count: int
    score_method: str = Field(pattern=SCORE_METHOD_PATTERN)
    component_risks_json: list[dict]
    computation_notes: str | None = None
    computed_by_user_id: UUID | None = None
    computed_at: datetime
    created_at: datetime


class EntityRiskScoreByBand(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    none: int = 0


class EntityRiskScoreTypeSummary(BaseModel):
    total_scored: int
    by_band: EntityRiskScoreByBand
    avg_composite_score: float
    last_computed_at: datetime | None = None


class EntityRiskScoreSummaryItem(BaseModel):
    entity_type: str = Field(pattern=ENTITY_TYPE_PATTERN)
    entity_id: UUID
    entity_label: str
    composite_score: float
    score_band: str = Field(pattern=SCORE_BAND_PATTERN)
    computed_at: datetime


class EntityRiskScoreSummaryResponse(BaseModel):
    by_entity_type: dict[str, EntityRiskScoreTypeSummary]
    highest_risk_entities: list[EntityRiskScoreSummaryItem]
