from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CarbonEmissionsReadingIngest(BaseModel):
    scope: str = Field(pattern="^(scope1|scope2|scope3)$")
    source: str = Field(min_length=1, max_length=120)
    period_start: date
    period_end: date
    value: Decimal = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)
    business_unit_id: UUID | None = None
    source_record_id: str | None = Field(default=None, max_length=255)
    raw_payload: dict | None = None


class CarbonEmissionsReadingRead(BaseModel):
    id: UUID
    organization_id: UUID
    scope: str
    source: str
    period_start: date
    period_end: date
    value: Decimal
    unit: str
    business_unit_id: UUID | None = None
    source_record_id: str | None = None
    raw_payload: dict
    ingested_at: datetime

    model_config = {"from_attributes": True}


class CarbonAccountingDashboard(BaseModel):
    totals_by_scope: dict[str, str]
    totals_by_period: list[dict]
    totals_by_business_unit: list[dict]
    reading_count: int
    canonical_unit: str
