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
    # True when the search backend (Meilisearch) could not be reached and this response is a
    # degraded empty-result fallback rather than a real (possibly also empty) search result.
    # Search is explicitly a best-effort cache over source-of-truth Postgres rows elsewhere in
    # this codebase (see search_indexing_service.py) -- callers should treat `degraded=True` as
    # "search is temporarily unavailable, not that nothing matched" and may want to retry later.
    degraded: bool = False
    degraded_reason: str | None = None
