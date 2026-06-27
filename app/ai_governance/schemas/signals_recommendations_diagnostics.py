import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AIRiskSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    signal_type: str
    signal_description: str
    detected_at: datetime
    severity: str
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class AIRiskSignalReviewRequest(BaseModel):
    action: str = Field(pattern="^(acknowledge|action_taken|dismiss)$")
    notes: str | None = None


class AIRiskRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    source_type: str
    recommendation_text: str
    recommendation_category: str
    priority: str
    status: str
    source_ref_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AIGovEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID | None
    event_type: str
    actor_id: uuid.UUID | None
    actor_type: str
    event_data: dict
    created_at: datetime


class AIGovEventSummaryRead(BaseModel):
    total_events_30d: int
    by_event_type: dict[str, int]
    systems_with_most_events: list[dict]
