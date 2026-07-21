import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MonitoringConfigCreate(BaseModel):
    metric_type: str
    threshold_value: Decimal
    comparison_direction: str
    alert_on_breach: bool = True
    check_frequency: str | None = None
    baseline_value: Decimal | None = None
    api_key: str | None = Field(default=None, min_length=12, max_length=255)


class MonitoringConfigUpdate(BaseModel):
    metric_type: str | None = None
    threshold_value: Decimal | None = None
    comparison_direction: str | None = None
    alert_on_breach: bool | None = None
    check_frequency: str | None = None
    baseline_value: Decimal | None = None
    api_key: str | None = Field(default=None, min_length=12, max_length=255)
    is_active: bool | None = None


class MonitoringConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    metric_type: str
    threshold_value: Decimal
    comparison_direction: str
    alert_on_breach: bool
    check_frequency: str | None
    baseline_value: Decimal | None
    baseline_model_version: str | None = None
    last_checked_at: datetime | None
    last_reading_value: Decimal | None
    is_active: bool
    api_key_configured: bool = False
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


#: Substrings that must never appear in a field name on any threshold-registry schema.
#: The registry is the one monitoring surface designed to be read by an external
#: collector, so a credential added to it later would leave core over the wire rather
#: than merely into a logged-in UI. Enforced by a test that inspects the declared
#: fields, so it fails when someone ADDS such a field -- an omission-by-convention
#: cannot do that.
REGISTRY_FORBIDDEN_FIELD_FRAGMENTS = ("api_key", "hash", "secret", "token", "password", "credential")


class ThresholdRegistryEntry(BaseModel):
    """One active threshold, as an external collector needs to see it.

    Deliberately NOT `MonitoringConfigRead`. That schema serves the logged-in UI and
    carries `api_key_configured`; this one is the machine-facing contract, and the
    smaller its field set, the less there is to leak. It exposes what to measure and
    what core will compare against -- never how to authenticate as the config.
    """

    model_config = ConfigDict(from_attributes=True)

    config_id: uuid.UUID
    ai_system_id: uuid.UUID
    metric_type: str
    tier: str
    escalation_order: int
    threshold_value: Decimal
    threshold_operator: str
    comparison_direction: str
    obligation_id: uuid.UUID | None
    workflow_to_trigger: str
    check_frequency: str | None
    baseline_value: Decimal | None
    collection_hint: str | None = None


class ThresholdRegistryRead(BaseModel):
    organization_id: uuid.UUID
    generated_at: datetime
    total: int
    thresholds: list[ThresholdRegistryEntry]


class MonitoringReadingCreate(BaseModel):
    config_id: uuid.UUID
    value: Decimal
    source_tool: str | None = Field(default=None, max_length=100)


class MonitoringReadingInboundCreate(BaseModel):
    config_id: uuid.UUID
    value: Decimal
    metric_type: str | None = None
    source_tool: str | None = Field(default=None, max_length=100)


class MonitoringReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    # Both optional since 0321. A reading may predate any threshold config
    # (config_id NULL), and a tiered reading has no single-config verdict
    # (within_threshold NULL -- its per-tier verdicts live in
    # ai_monitoring_breach_events). Declaring these non-optional made the
    # readings-list and monitoring-dashboard endpoints return 500 on such a row.
    config_id: uuid.UUID | None
    value: Decimal
    reading_source: str
    source_tool: str | None
    within_threshold: bool | None
    created_at: datetime


class MonitoringDashboardItem(BaseModel):
    config_id: uuid.UUID
    metric_type: str
    is_active: bool
    threshold_value: Decimal
    comparison_direction: str
    last_reading_value: Decimal | None
    within_threshold: bool | None
    last_checked_at: datetime | None
    baseline_value: Decimal | None = None
    drift_pct: Decimal | None = Field(
        default=None,
        description="Absolute percentage deviation of the latest reading from baseline_value.",
    )
    drift_detected: bool = Field(
        default=False,
        description="True when the latest reading has drifted more than 20% from baseline_value.",
    )
    baseline_reassessment_required: bool = Field(
        default=False,
        description=(
            "True when the AI system's model_version has changed since this metric's "
            "baseline was recorded, meaning the baseline may no longer be representative."
        ),
    )


class MonitoringDashboardRead(BaseModel):
    configs: list[MonitoringDashboardItem]
    recent_breaches: list[MonitoringReadingRead]


class MonitoringReadingHistorySummary(BaseModel):
    count_in_page: int
    min_value: Decimal | None
    max_value: Decimal | None
    avg_value: Decimal | None
    breach_count_in_page: int
    trend_direction: str | None
    breach_streak: int
    sustained_degradation: bool
    pct_from_baseline: float | None


class MonitoringReadingHistoryRead(BaseModel):
    config_id: uuid.UUID
    metric_type: str
    total: int
    readings: list[MonitoringReadingRead]
    summary: MonitoringReadingHistorySummary
