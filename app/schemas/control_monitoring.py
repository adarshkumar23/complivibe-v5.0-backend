from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

MONITORING_TYPE_PATTERN = "^(manual_check|evidence_freshness|test_frequency|task_completion|recertification_due)$"
MONITORING_STATUS_PATTERN = "^(active|inactive|archived)$"
CHECK_FREQUENCY_PATTERN = "^(daily|weekly|monthly|quarterly|annually)$"
CHECK_STATUS_PATTERN = "^(pass|fail|warning|not_checked|skipped)$"


class ControlMonitoringDefinitionCreate(BaseModel):
    control_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    monitoring_type: str = Field(pattern=MONITORING_TYPE_PATTERN)
    check_frequency: str = Field(pattern=CHECK_FREQUENCY_PATTERN)
    owner_user_id: UUID
    # Optional explicit due date, mirroring ControlTestDefinitionCreate.next_due_at. Lets callers
    # backdate a definition (e.g. migrating existing monitoring cadences, or seeding a definition
    # that is already overdue) instead of always defaulting to "never due until first check".
    next_check_due_at: datetime | None = None
    tags_json: dict | list | None = None
    notes: str | None = None


class ControlMonitoringDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    monitoring_type: str | None = Field(default=None, pattern=MONITORING_TYPE_PATTERN)
    check_frequency: str | None = Field(default=None, pattern=CHECK_FREQUENCY_PATTERN)
    owner_user_id: UUID | None = None
    next_check_due_at: datetime | None = None
    tags_json: dict | list | None = None
    notes: str | None = None


class ControlMonitoringDefinitionRead(BaseModel):
    id: UUID
    organization_id: UUID
    control_id: UUID
    name: str
    description: str | None = None
    monitoring_type: str
    status: str
    check_frequency: str
    owner_user_id: UUID
    last_checked_at: datetime | None = None
    next_check_due_at: datetime | None = None
    tags_json: dict | list | None = None
    notes: str | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    archive_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ControlMonitoringArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ControlMonitoringResultRecordRequest(BaseModel):
    check_status: str = Field(pattern=CHECK_STATUS_PATTERN)
    result_summary: str | None = None
    result_detail_json: dict | list | None = None


class ControlMonitoringResultRead(BaseModel):
    id: UUID
    organization_id: UUID
    definition_id: UUID
    control_id: UUID
    check_status: str
    result_summary: str | None = None
    result_detail_json: dict | list | None = None
    checked_by_user_id: UUID
    checked_at: datetime
    next_check_due_at: datetime | None = None
    created_at: datetime


class ControlMonitoringSummary(BaseModel):
    total_definitions: int
    active_definitions: int
    inactive_definitions: int
    archived_definitions: int
    definitions_due_now: int
    total_results: int
    by_monitoring_type: dict[str, int]
    by_check_status: dict[str, int]
