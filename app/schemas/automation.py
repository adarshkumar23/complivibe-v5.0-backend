from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class AutomationRuleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    trigger_type: str = Field(pattern="^(manual_scan|scheduled_placeholder|entity_state_change_placeholder)$")
    condition_type: str
    condition_config_json: dict | None = None
    action_type: str
    action_config_json: dict | None = None
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


class AutomationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    trigger_type: str | None = Field(default=None, pattern="^(manual_scan|scheduled_placeholder|entity_state_change_placeholder)$")
    condition_type: str | None = None
    condition_config_json: dict | None = None
    action_type: str | None = None
    action_config_json: dict | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")


class AutomationRuleScheduleUpdate(BaseModel):
    schedule_enabled: bool
    schedule_cadence: str | None = Field(default=None, pattern="^(hourly|daily|weekly|monthly)$")
    schedule_timezone: str | None = Field(default=None, max_length=64)
    schedule_start_at: datetime | None = None
    schedule_end_at: datetime | None = None
    schedule_window_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    schedule_window_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    run_mode: str | None = Field(default=None, pattern="^(live|dry_run)$")
    version_notes: str | None = None


class AutomationRuleRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    trigger_type: str
    condition_type: str
    condition_config_json: dict | None = None
    action_type: str
    action_config_json: dict | None = None
    status: str
    priority: str
    last_run_at: datetime | None = None
    schedule_enabled: bool
    schedule_cadence: str | None = None
    schedule_timezone: str
    schedule_start_at: datetime | None = None
    schedule_end_at: datetime | None = None
    schedule_window_start: str | None = None
    schedule_window_end: str | None = None
    next_run_at: datetime | None = None
    last_scheduled_run_at: datetime | None = None
    last_dry_run_at: datetime | None = None
    run_mode: str
    version: int
    version_notes: str | None = None
    created_by_user_id: UUID | None = None


class AutomationRuleVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    rule_id: UUID
    version: int
    name: str
    description: str | None = None
    trigger_type: str
    condition_type: str
    condition_config_json: dict | None = None
    action_type: str
    action_config_json: dict | None = None
    schedule_config_json: dict | None = None
    status: str
    version_notes: str | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime


class AutomationActionLogRead(BaseModel):
    id: UUID
    organization_id: UUID
    rule_id: UUID
    execution_id: UUID
    entity_type: str
    entity_id: UUID
    action_type: str
    action_status: str
    idempotency_key: str | None = None
    created_task_id: UUID | None = None
    created_email_outbox_id: UUID | None = None
    skipped_reason: str | None = None
    error_message: str | None = None
    created_at: datetime


class AutomationExecutionRead(UUIDTimestampSchema):
    organization_id: UUID
    rule_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    matched_count: int
    action_count: int
    skipped_count: int
    error_count: int
    idempotency_key: str | None = None
    trigger_source: str
    dry_run: bool
    rule_version: int | None = None
    scheduled_run_at: datetime | None = None
    idempotency_scope: str | None = None
    summary_json: dict | None = None
    created_by_user_id: UUID | None = None


class AutomationExecutionDetail(AutomationExecutionRead):
    action_logs: list[AutomationActionLogRead]


class AutomationRunResponse(BaseModel):
    execution_id: UUID
    status: str
    matched_count: int
    action_count: int
    skipped_count: int
    error_count: int
    dry_run: bool


class AutomationScanRunRequest(BaseModel):
    dry_run: bool = False
    limit: int = Field(default=25, ge=1, le=200)


class AutomationScanResponse(BaseModel):
    execution_count: int
    executions: list[AutomationRunResponse]


class AutomationSummary(BaseModel):
    active_rules: int
    inactive_rules: int
    archived_rules: int
    executions_last_24h: int
    actions_created_last_24h: int
    duplicate_actions_skipped_last_24h: int
    failed_actions_last_24h: int


class AutomationScheduleSummary(BaseModel):
    scheduled_rules: int
    enabled_schedules: int
    due_now: int
    disabled_schedules: int
    last_scheduled_run_at: datetime | None = None
    next_due_run_at: datetime | None = None
    dry_run_executions_last_24h: int
    live_scheduled_executions_last_24h: int
