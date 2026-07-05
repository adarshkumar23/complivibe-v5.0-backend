from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchHit(BaseModel):
    """A single cross-entity search result.

    Documents differ in shape per entity_type (a risk hit has severity/
    treatment_strategy, a vendor hit has risk_tier, etc.), so this model
    only pins down the fields every hit is guaranteed to carry and allows
    the rest through as-is.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    entity_type: str
    id: str
    organization_id: str | None = None
    score: float | None = Field(default=None, alias="_rankingScore")


class SearchResponse(BaseModel):
    query: str
    took_ms: int
    hits: list[SearchHit]
