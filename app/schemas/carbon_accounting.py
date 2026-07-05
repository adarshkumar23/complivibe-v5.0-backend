from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CarbonEmissionsReadingIngest(BaseModel):
    scope: str = Field(pattern="^(scope1|scope2|scope3)$")
    scope3_category: str | None = Field(
        default=None,
        description=(
            "Required when scope='scope3'. One of the 15 GHG Protocol Corporate Value Chain "
            "(Scope 3) Standard categories, e.g. 'purchased_goods_and_services', 'business_travel'."
        ),
    )
    source: str = Field(min_length=1, max_length=120)
    period_start: date
    period_end: date
    value: Decimal = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)
    business_unit_id: UUID | None = None
    source_record_id: str | None = Field(default=None, max_length=255)
    emission_factor_source: str | None = Field(
        default=None,
        max_length=120,
        description="Provenance of the emission factor used to derive value, e.g. 'epa_egrid', 'defra_ghg_conversion_factors', 'client_supplied'.",
    )
    emission_factor_version: str | None = Field(
        default=None,
        max_length=40,
        description="Version/vintage of the emission factor dataset, e.g. 'eGRID2023rev1', 'DEFRA-2025'.",
    )
    raw_payload: dict | None = None

    @model_validator(mode="after")
    def _check_scope3_category(self) -> "CarbonEmissionsReadingIngest":
        if self.scope == "scope3" and not self.scope3_category:
            raise ValueError("scope3_category is required when scope is 'scope3'")
        if self.scope != "scope3" and self.scope3_category:
            raise ValueError("scope3_category must not be set unless scope is 'scope3'")
        return self


class CarbonEmissionsReadingRead(BaseModel):
    id: UUID
    organization_id: UUID
    scope: str
    scope3_category: str | None = None
    source: str
    period_start: date
    period_end: date
    value: Decimal
    unit: str
    business_unit_id: UUID | None = None
    source_record_id: str | None = None
    emission_factor_source: str | None = None
    emission_factor_version: str | None = None
    raw_payload: dict
    ingested_at: datetime
    corrected_at: datetime | None = None

    model_config = {"from_attributes": True}


class CarbonAccountingDashboard(BaseModel):
    totals_by_scope: dict[str, str]
    totals_by_scope3_category: list[dict]
    totals_by_period: list[dict]
    totals_by_business_unit: list[dict]
    reading_count: int
    canonical_unit: str
    insights: list[str] = Field(default_factory=list)
