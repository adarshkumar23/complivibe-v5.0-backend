import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LLMObservabilityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    event_type: str
    source_tool: str
    metric_type: str
    value: Decimal
    is_flagged: bool
    flag_reason: str | None
    details_json: dict | list | None
    created_at: datetime


class TracePollRequest(BaseModel):
    public_key: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=500)


class HallucinationCheckRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    actual_output: str = Field(min_length=1, max_length=20000)
    context: list[str] = Field(min_length=1)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class CostReadingRequest(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    input_price_per_million: Decimal | None = Field(default=None, ge=0)
    output_price_per_million: Decimal | None = Field(default=None, ge=0)


class RAGEvaluationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    retrieved_contexts: list[str] = Field(min_length=1)
    actual_output: str = Field(min_length=1, max_length=20000)


class LLMObservabilitySummaryRead(BaseModel):
    ai_system_id: uuid.UUID
    window_days: int
    total_events: int
    flagged_events: int
    total_cost_usd_30d: Decimal
    event_counts_by_type: dict[str, int]
    recent_events: list[LLMObservabilityEventRead]
