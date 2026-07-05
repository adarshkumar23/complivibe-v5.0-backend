from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

GEOPOLITICAL_CATEGORY_PATTERN = (
    "^(conflict|sanctions|political_instability|trade_restriction|regulatory_change|other)$"
)
GEOPOLITICAL_SEVERITY_PATTERN = "^(low|medium|high|critical)$"


class GeopoliticalIngestRequest(BaseModel):
    region_query: str = Field(min_length=1, max_length=200)
    max_records: int = Field(default=20, ge=1, le=100)


class GeopoliticalRiskSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    region: str
    category: str = Field(pattern=GEOPOLITICAL_CATEGORY_PATTERN)
    severity: str = Field(pattern=GEOPOLITICAL_SEVERITY_PATTERN)
    source: str
    source_url: str | None = None
    headline: str | None = None
    detected_at: datetime
    source_error: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class GeopoliticalIngestResponse(BaseModel):
    status: str  # "ok" | "error"
    source: str
    region_query: str
    signals_created: int
    source_error: str | None = None
    signals: list[GeopoliticalRiskSignalResponse] = Field(default_factory=list)


class VendorGeopoliticalExposureCreate(BaseModel):
    vendor_id: UUID
    region: str = Field(min_length=1, max_length=100)
    is_primary: bool = False
    notes: str | None = None


class VendorGeopoliticalExposureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    vendor_id: UUID
    region: str
    is_primary: bool
    notes: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ExposedVendorRegion(BaseModel):
    region: str
    signal_count: int
    max_severity: str = Field(pattern=GEOPOLITICAL_SEVERITY_PATTERN)


class ExposedVendorSummary(BaseModel):
    vendor_id: UUID
    vendor_name: str
    business_unit_id: UUID | None = None
    exposed_regions: list[ExposedVendorRegion]
    overall_max_severity: str = Field(pattern=GEOPOLITICAL_SEVERITY_PATTERN)
    total_signal_count: int


class GeopoliticalSummaryResponse(BaseModel):
    organization_id: UUID
    regions_with_signals: list[str]
    exposed_vendors: list[ExposedVendorSummary]
    vendor_count_exposed: int
    highest_severity_observed: str | None = None
