from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

DEADLINE_TYPE_PATTERN = "^(evidence_recertification|control_review|policy_review|vendor_assessment|framework_review|regulatory_filing|audit_preparation|custom)$"
DEADLINE_STATUS_PATTERN = "^(upcoming|overdue|completed|waived|cancelled)$"
DEADLINE_PRIORITY_PATTERN = "^(critical|high|medium|low)$"
LINKED_ENTITY_TYPE_PATTERN = "^(control|evidence|policy|vendor|framework|task)$"
DEADLINE_EVENT_TYPE_PATTERN = "^(reminder_due|overdue_detected|completed|waived|cancelled)$"


class ComplianceDeadlineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    deadline_type: str = Field(pattern=DEADLINE_TYPE_PATTERN)
    due_date: date
    priority: str = Field(default="medium", pattern=DEADLINE_PRIORITY_PATTERN)
    owner_user_id: UUID
    linked_entity_type: str | None = Field(default=None, pattern=LINKED_ENTITY_TYPE_PATTERN)
    linked_entity_id: UUID | None = None
    reminder_days_before: int = Field(default=7, ge=0, le=365)
    tags_json: dict | list | None = None
    notes: str | None = None


class ComplianceDeadlineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    deadline_type: str | None = Field(default=None, pattern=DEADLINE_TYPE_PATTERN)
    due_date: date | None = None
    priority: str | None = Field(default=None, pattern=DEADLINE_PRIORITY_PATTERN)
    owner_user_id: UUID | None = None
    linked_entity_type: str | None = Field(default=None, pattern=LINKED_ENTITY_TYPE_PATTERN)
    linked_entity_id: UUID | None = None
    reminder_days_before: int | None = Field(default=None, ge=0, le=365)
    tags_json: dict | list | None = None
    notes: str | None = None


class ComplianceDeadlineCompleteRequest(BaseModel):
    completion_notes: str = Field(min_length=1, max_length=4000)


class ComplianceDeadlineWaiveRequest(BaseModel):
    waiver_reason: str = Field(min_length=1, max_length=4000)


class ComplianceDeadlineCancelRequest(BaseModel):
    cancellation_reason: str = Field(min_length=1, max_length=4000)


class ComplianceDeadlineEvaluateRequest(BaseModel):
    dry_run: bool = True


class ComplianceDeadlineRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    description: str | None = None
    deadline_type: str
    due_date: date
    status: str
    priority: str
    owner_user_id: UUID
    linked_entity_type: str | None = None
    linked_entity_id: UUID | None = None
    reminder_days_before: int
    last_reminder_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by_user_id: UUID | None = None
    completion_notes: str | None = None
    waiver_reason: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    cancellation_reason: str | None = None
    tags_json: dict | list | None = None
    notes: str | None = None
    created_by_user_id: UUID
    days_until_due: int | None = None
    recommended_status: str | None = None
    is_status_stale: bool = False
    context_flags: list[str] = []


class ComplianceDeadlineEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    deadline_id: UUID
    event_type: str
    dry_run: bool
    outbox_queued: bool
    event_metadata_json: dict | list | None = None
    created_at: datetime


class ComplianceDeadlineEvaluateResponse(BaseModel):
    dry_run: bool
    deadlines_evaluated: int
    overdue_marked: int
    reminders_triggered: int
    events_created: int
    events_skipped_duplicates: int


class ComplianceDeadlineSummary(BaseModel):
    total_deadlines: int
    upcoming_deadlines: int
    overdue_deadlines: int
    completed_deadlines: int
    waived_deadlines: int
    cancelled_deadlines: int
    due_within_7_days: int
    high_risk_overdue_count: int
    stale_status_count: int
    deadlines_without_active_owner: int
    by_status: dict[str, int]
    by_deadline_type: dict[str, int]
    by_priority: dict[str, int]
