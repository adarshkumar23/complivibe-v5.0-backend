import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DataQualityConfigCreate(BaseModel):
    data_asset_id: uuid.UUID
    metric_type: str
    threshold_value: Decimal
    comparison_direction: str
    alert_on_breach: bool = True
    measurement_frequency: str | None = None
    description: str | None = None


class DataQualityConfigUpdate(BaseModel):
    metric_type: str | None = None
    threshold_value: Decimal | None = None
    comparison_direction: str | None = None
    alert_on_breach: bool | None = None
    measurement_frequency: str | None = None
    description: str | None = None
    is_active: bool | None = None


class DataQualityConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    data_asset_id: uuid.UUID
    metric_type: str
    threshold_value: Decimal
    comparison_direction: str
    alert_on_breach: bool
    measurement_frequency: str | None
    description: str | None
    is_active: bool
    last_checked_at: datetime | None
    last_value: Decimal | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    expected_check_interval_hours: int | None = None
    hours_since_last_check: int | None = None
    check_stale: bool = False
    context_flags: list[str] = []


class DataQualityReadingCreate(BaseModel):
    value: Decimal
    source_tool: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class DataQualityReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    config_id: uuid.UUID
    value: Decimal
    reading_source: str
    source_tool: str | None
    within_threshold: bool
    notes: str | None
    created_at: datetime
    threshold_delta: Decimal | None = None
    breach_magnitude: str | None = None
    context_flags: list[str] = []


class MetricDashboardItem(BaseModel):
    configs: int
    breach_rate: float


class AssetBreachItem(BaseModel):
    asset_id: str
    asset_name: str
    breach_count: int


class DataQualityDashboardRead(BaseModel):
    total_configs: int
    active_configs: int
    recent_breaches_7d: int
    stale_config_count: int = 0
    high_risk_breach_count_7d: int = 0
    by_metric_type: dict[str, MetricDashboardItem]
    assets_with_breaches: list[AssetBreachItem]
    context_flags: list[str] = []
