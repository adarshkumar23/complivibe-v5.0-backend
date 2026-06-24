from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

ALERT_TYPE_PATTERN = "^(overdue_check|consecutive_fails|evidence_gap|task_overdue|risk_threshold_breach|manual)$"
ALERT_SEVERITY_PATTERN = "^(critical|high|medium|low|info)$"
ALERT_STATUS_PATTERN = "^(open|acknowledged|resolved|dismissed)$"


class ControlMonitoringAlertCreate(BaseModel):
    rule_id: UUID | None = None
    definition_id: UUID | None = None
    control_id: UUID | None = None
    severity: str = Field(default="medium", pattern=ALERT_SEVERITY_PATTERN)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    alert_context_json: dict | list | None = None
    assigned_to_user_id: UUID | None = None


class ControlMonitoringAlertAssignRequest(BaseModel):
    assigned_to_user_id: UUID | None = None


class ControlMonitoringAlertResolveRequest(BaseModel):
    resolution_notes: str = Field(min_length=1, max_length=4000)


class ControlMonitoringAlertDismissRequest(BaseModel):
    dismissal_reason: str = Field(min_length=1, max_length=4000)


class ControlMonitoringAlertRead(UUIDTimestampSchema):
    organization_id: UUID
    rule_id: UUID | None = None
    definition_id: UUID | None = None
    control_id: UUID | None = None
    alert_type: str
    severity: str
    status: str
    title: str
    description: str | None = None
    alert_context_json: dict | list | None = None
    assigned_to_user_id: UUID | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by_user_id: UUID | None = None
    resolved_at: datetime | None = None
    resolved_by_user_id: UUID | None = None
    resolution_notes: str | None = None
    dismissed_at: datetime | None = None
    dismissed_by_user_id: UUID | None = None
    dismissal_reason: str | None = None


class ControlMonitoringAlertSummary(BaseModel):
    total_alerts: int
    open_alerts: int
    acknowledged_alerts: int
    resolved_alerts: int
    dismissed_alerts: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    by_alert_type: dict[str, int]
