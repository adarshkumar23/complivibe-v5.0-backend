from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


COMPETITOR_PATTERN = "^(vanta|drata|sprinto|scrut|onetrust|credo_ai)$"
PRICING_MODEL_PATTERN = "^(contact_sales|tiered_quote|starting_from|custom_package)$"


class CompetitorPricingEntryRead(BaseModel):
    id: UUID
    competitor_key: str = Field(pattern=COMPETITOR_PATTERN)
    competitor_name: str
    pricing_model: str = Field(pattern=PRICING_MODEL_PATTERN)
    public_pricing_available: bool
    pricing_summary: str
    source_url: str
    source_excerpt: str | None = None
    currency: str | None = None
    starting_price_amount: float | None = None
    starting_price_unit: str | None = None
    last_verified_at: datetime
    metadata_json: dict


class CompetitorPricingSnapshotRead(BaseModel):
    version_id: UUID
    source_note: str | None = None
    published_at: datetime
    last_updated: datetime
    entries: list[CompetitorPricingEntryRead]


class CompetitorPricingEntryRefresh(BaseModel):
    competitor_key: str = Field(pattern=COMPETITOR_PATTERN)
    competitor_name: str = Field(min_length=1, max_length=64)
    pricing_model: str = Field(pattern=PRICING_MODEL_PATTERN)
    public_pricing_available: bool = False
    pricing_summary: str = Field(min_length=1)
    source_url: str = Field(min_length=1, max_length=512)
    source_excerpt: str | None = None
    currency: str | None = Field(default=None, max_length=8)
    starting_price_amount: float | None = None
    starting_price_unit: str | None = Field(default=None, max_length=32)
    last_verified_at: datetime
    metadata_json: dict = Field(default_factory=dict)


class CompetitorPricingRefreshRequest(BaseModel):
    source_note: str | None = None
    entries: list[CompetitorPricingEntryRefresh] = Field(min_length=1)


class OnboardingSelectPlanRead(BaseModel):
    available_plans: list[dict]
    competitor_pricing: CompetitorPricingSnapshotRead
