from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import UUIDTimestampSchema

KRI_METRIC_TYPE_PATTERN = (
    "^(control_expiry_rate|evidence_gap_rate|overdue_task_rate|vendor_high_risk_count|open_alert_count|policy_overdue_review|custom)$"
)
KRI_STATUS_PATTERN = "^(green|amber|red|not_calculated)$"


class RiskIndicatorLinkedRiskSummary(BaseModel):
    id: UUID
    title: str
    status: str
    severity: str


class RiskIndicatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    metric_type: str = Field(pattern=KRI_METRIC_TYPE_PATTERN)
    target_value: float
    warning_threshold: float
    critical_threshold: float
    owner_user_id: UUID
    linked_risk_id: UUID | None = None
    notes: str | None = None
    tags_json: dict | list | None = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> "RiskIndicatorCreate":
        if self.warning_threshold >= self.critical_threshold:
            raise ValueError("warning_threshold must be less than critical_threshold")
        return self


class RiskIndicatorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    target_value: float | None = None
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    owner_user_id: UUID | None = None
    linked_risk_id: UUID | None = None
    notes: str | None = None
    tags_json: dict | list | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_thresholds_if_both_present(self) -> "RiskIndicatorUpdate":
        if self.warning_threshold is not None and self.critical_threshold is not None:
            if self.warning_threshold >= self.critical_threshold:
                raise ValueError("warning_threshold must be less than critical_threshold")
        return self


class RiskIndicatorArchiveRequest(BaseModel):
    archive_reason: str = Field(min_length=1, max_length=4000)


class RiskIndicatorRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    metric_type: str = Field(pattern=KRI_METRIC_TYPE_PATTERN)
    target_value: float
    warning_threshold: float
    critical_threshold: float
    current_value: float | None = None
    status: str = Field(pattern=KRI_STATUS_PATTERN)
    owner_user_id: UUID
    linked_risk_id: UUID | None = None
    last_calculated_at: datetime | None = None
    notes: str | None = None
    tags_json: dict | list | None = None
    is_active: bool
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    archive_reason: str | None = None


class RiskIndicatorDetail(RiskIndicatorRead):
    linked_risk_summary: RiskIndicatorLinkedRiskSummary | None = None


class RiskIndicatorSummary(BaseModel):
    total_indicators: int
    by_status: dict[str, int]
    by_metric_type: dict[str, int]
    last_calculated_at: datetime | None = None
    critical_count: int
    warning_count: int
