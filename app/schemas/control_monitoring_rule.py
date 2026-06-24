from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

RULE_STATUS_PATTERN = "^(active|inactive|archived)$"
RULE_TYPE_PATTERN = "^(overdue_check|consecutive_fails|evidence_gap|task_overdue|risk_threshold_breach)$"
ACTION_TYPE_PATTERN = "^(create_alert|queue_reminder|create_task)$"


class ControlMonitoringRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rule_type: str = Field(pattern=RULE_TYPE_PATTERN)
    condition_json: dict
    action_type: str = Field(pattern=ACTION_TYPE_PATTERN)
    action_config_json: dict
    scope_definition_ids: list[UUID] | None = None


class ControlMonitoringRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    rule_type: str | None = Field(default=None, pattern=RULE_TYPE_PATTERN)
    condition_json: dict | None = None
    action_type: str | None = Field(default=None, pattern=ACTION_TYPE_PATTERN)
    action_config_json: dict | None = None
    scope_definition_ids: list[UUID] | None = None


class ControlMonitoringRuleArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ControlMonitoringRuleEvaluateRequest(BaseModel):
    dry_run: bool = True


class ControlMonitoringRuleRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    status: str
    rule_type: str
    condition_json: dict
    action_type: str
    action_config_json: dict
    scope_definition_ids: list[UUID] | None = None
    last_evaluated_at: datetime | None = None
    created_by_user_id: UUID
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    archive_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ControlMonitoringRuleExecutionRead(BaseModel):
    id: UUID
    organization_id: UUID
    rule_id: UUID
    triggered_at: datetime
    dry_run: bool
    matched_count: int
    action_count: int
    skipped_count: int
    execution_summary_json: dict
    created_at: datetime


class ControlMonitoringRuleEvaluateResponse(BaseModel):
    dry_run: bool
    evaluated_rules: int
    executions: list[ControlMonitoringRuleExecutionRead]


class ControlMonitoringRuleSummary(BaseModel):
    total_rules: int
    active_rules: int
    inactive_rules: int
    archived_rules: int
    total_executions: int
    total_dry_runs: int
    total_live_runs: int
    total_matched: int
    total_actions: int
    total_skipped: int
    by_rule_type: dict[str, int]
    by_action_type: dict[str, int]
