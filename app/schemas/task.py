from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class TaskLinkedEntitySummary(BaseModel):
    entity_type: str
    id: str
    title: str
    status: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    task_type: str = Field(
        default="general",
        pattern="^(risk_treatment|control_remediation|evidence_request|framework_gap|obligation_review|audit_request|general)$",
    )
    owner_user_id: UUID | None = None
    due_date: datetime | None = None
    linked_entity_type: str | None = Field(
        default=None,
        pattern="^(risk|control|evidence|obligation|framework|organization_framework|general)$",
    )
    linked_entity_id: UUID | None = None
    metadata_json: dict | None = None
    notify_assignee: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|blocked|completed|cancelled|archived)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    owner_user_id: UUID | None = None
    due_date: datetime | None = None
    metadata_json: dict | None = None


class TaskRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    description: str | None = None
    status: str
    priority: str
    task_type: str
    owner_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
    completed_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    linked_entity_type: str | None = None
    linked_entity_id: UUID | None = None
    source: str
    reminder_status: str
    last_reminder_at: datetime | None = None
    metadata_json: dict | None = None
    # Derived, not persisted: whether this task is currently past due (only
    # meaningful while still open/in_progress/blocked) and by how much.
    is_overdue: bool = False
    overdue_by_hours: float | None = None


class TaskDetail(TaskRead):
    linked_entity_summary: TaskLinkedEntitySummary | None = None
    # True when the linked entity's own status suggests the reason this task
    # exists has already been resolved elsewhere (e.g. the risk it was meant
    # to treat was separately marked mitigated/accepted) while the task
    # itself is still open -- flagged instead of silently left stale.
    linked_entity_stale: bool = False


class TaskCompleteRequest(BaseModel):
    completion_notes: str | None = None


class TaskCancelRequest(BaseModel):
    cancellation_reason: str = Field(min_length=3, max_length=2000)


class RiskTreatmentTaskCreate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    owner_user_id: UUID | None = None
    due_date: datetime | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    notify_assignee: bool = False


class TaskNotifyResponse(BaseModel):
    task_id: UUID
    outbox_email_id: UUID
    status: str


class TaskReminderQueueRequest(BaseModel):
    due_within_days: int = Field(default=3, ge=0, le=90)
    overdue_only: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class TaskReminderQueueResponse(BaseModel):
    queued_count: int
    outbox_email_ids: list[UUID]


class TaskSummary(BaseModel):
    total_tasks: int
    open_tasks: int
    in_progress_tasks: int
    blocked_tasks: int
    completed_tasks: int
    cancelled_tasks: int
    overdue_tasks: int
    due_soon_tasks: int
    unassigned_tasks: int
    urgent_open_tasks: int
