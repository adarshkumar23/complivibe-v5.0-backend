import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.ai_monitoring_config import SELECTABLE_WORKFLOW_VALUES, THRESHOLD_OPERATORS


#: suspend_system is absent by construction -- see SELECTABLE_WORKFLOW_VALUES. It has
#: no implementation, and offering it would let a customer believe their AI system gets
#: halted on breach when nothing would happen.
WORKFLOW_TO_TRIGGER_PATTERN = "^(" + "|".join(SELECTABLE_WORKFLOW_VALUES) + ")$"
THRESHOLD_OPERATOR_PATTERN = "^(" + "|".join(THRESHOLD_OPERATORS) + ")$"


class MonitoringConfigCreate(BaseModel):
    metric_type: str
    threshold_value: Decimal
    comparison_direction: str
    alert_on_breach: bool = True
    check_frequency: str | None = None
    baseline_value: Decimal | None = None
    api_key: str | None = Field(default=None, min_length=12, max_length=255)
    # --- patent P4 compliance-decision layer ---
    # Defaults reproduce the pre-P4 behaviour exactly, so an existing client that sends
    # none of these gets the same config it always did.
    tier: str = Field(default="default", min_length=1, max_length=32)
    escalation_order: int = Field(default=0, ge=0)
    threshold_operator: str | None = Field(default=None, pattern=THRESHOLD_OPERATOR_PATTERN)
    workflow_to_trigger: str = Field(default="create_alert", pattern=WORKFLOW_TO_TRIGGER_PATTERN)
    obligation_id: uuid.UUID | None = None


class MonitoringConfigUpdate(BaseModel):
    metric_type: str | None = None
    threshold_value: Decimal | None = None
    comparison_direction: str | None = None
    alert_on_breach: bool | None = None
    check_frequency: str | None = None
    baseline_value: Decimal | None = None
    api_key: str | None = Field(default=None, min_length=12, max_length=255)
    is_active: bool | None = None
    tier: str | None = Field(default=None, min_length=1, max_length=32)
    escalation_order: int | None = Field(default=None, ge=0)
    threshold_operator: str | None = Field(default=None, pattern=THRESHOLD_OPERATOR_PATTERN)
    workflow_to_trigger: str | None = Field(default=None, pattern=WORKFLOW_TO_TRIGGER_PATTERN)
    obligation_id: uuid.UUID | None = None


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
    tier: str = "default"
    escalation_order: int = 0
    threshold_operator: str = "gte"
    workflow_to_trigger: str = "create_alert"
    obligation_id: uuid.UUID | None = None
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


#: Column/field-name fragments that mean a VERDICT rather than a measurement. The P4
#: satellite computes numbers; core alone decides what they mean. A payload carrying
#: `is_breach`, `severity` or `alert_level` would invert that, so the push is refused
#: rather than quietly stripped -- silently dropping the field would let a satellite
#: believe its verdict was accepted.
#:
#: Substring matching, so `is_breach`, `breach_flag` and `breached_at` are all caught.
#: Mirrors migration 0321's VERDICT_COLUMN_FRAGMENTS, which guards the same invariant at
#: the schema level.
VERDICT_FIELD_FRAGMENTS = (
    "breach",
    "severity",
    "violation",
    "alert_level",
    "verdict",
    "decision",
    "compliance_status",
    "threshold_exceeded",
    "risk_level",
    "within_threshold",
)


class P4MonitoringReadingPush(BaseModel):
    """One measurement pushed by the P4 monitoring satellite.

    `extra="forbid"` alone would reject a verdict field, but with a generic "unexpected
    keyword" message. The explicit pre-validator below names the offending field and
    says why, because a satellite author debugging a 422 should learn the boundary rule
    rather than guess at a typo.
    """

    model_config = ConfigDict(extra="forbid")

    ai_system_id: uuid.UUID
    metric_type: str = Field(min_length=1, max_length=64)
    value: Decimal
    # 'a' in-environment agent, 'b' external push, 'c' scheduled pull.
    collection_mode: str = Field(default="b", pattern="^(a|b|c)$")
    config_id: uuid.UUID | None = None
    sample_size: int | None = Field(default=None, ge=0)
    computed_by: str | None = Field(default=None, max_length=64)
    reported_at: datetime | None = None
    source_tool: str | None = Field(default=None, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def _refuse_verdict_fields(cls, data):
        if not isinstance(data, dict):
            return data
        offenders = sorted(
            key
            for key in data
            if any(fragment in str(key).lower() for fragment in VERDICT_FIELD_FRAGMENTS)
        )
        if offenders:
            raise ValueError(
                f"verdict-shaped field(s) not accepted: {', '.join(offenders)}. The "
                "satellite reports what was measured; core decides what it means. Send "
                "the value only."
            )
        return data


class P4MonitoringPushResult(BaseModel):
    reading_id: uuid.UUID
    organization_id: uuid.UUID
    breach_events: int
    tiers_dispatched: list[str]
