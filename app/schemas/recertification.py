from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EvidenceLinkedControlSummary(BaseModel):
    control_id: UUID
    title: str
    status: str


class DueEvidenceItemRead(BaseModel):
    evidence_id: UUID
    title: str
    review_status: str
    freshness_status: str
    valid_until: datetime | None = None
    due_reason: str
    priority: str
    owner_user_id: UUID | None = None
    linked_controls: list[EvidenceLinkedControlSummary] = []


class DueControlReassessmentRead(BaseModel):
    test_id: UUID
    control_id: UUID
    control_title: str
    test_name: str
    next_due_at: datetime | None = None
    due_status: str
    latest_result: str | None = None
    owner_user_id: UUID | None = None


class RecertificationPolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    scope_type: str
    scope_config_json: dict | None = None
    cadence: str
    lead_time_days: int = Field(default=14, ge=1, le=365)
    owner_user_id: UUID | None = None
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class RecertificationPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    scope_type: str | None = None
    scope_config_json: dict | None = None
    cadence: str | None = None
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    owner_user_id: UUID | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class RecertificationPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    scope_type: str
    scope_config_json: dict | None = None
    cadence: str
    lead_time_days: int
    owner_user_id: UUID | None = None
    status: str
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class RecertificationRunRequest(BaseModel):
    policy_id: UUID | None = None
    dry_run: bool = False
    notify_owner: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class ControlReassessmentRunRequest(BaseModel):
    policy_id: UUID | None = None
    dry_run: bool = False
    notify_owner: bool = False
    due_within_days: int = Field(default=7, ge=0, le=365)
    limit: int = Field(default=50, ge=1, le=200)


class RecertificationActionLogRead(BaseModel):
    id: UUID
    organization_id: UUID
    run_id: UUID
    policy_id: UUID | None = None
    entity_type: str
    entity_id: UUID
    action_type: str
    action_status: str
    idempotency_key: str
    created_task_id: UUID | None = None
    created_email_outbox_id: UUID | None = None
    skipped_reason: str | None = None
    error_message: str | None = None
    created_at: datetime


class RecertificationRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID | None = None
    run_type: str
    dry_run: bool
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    due_count: int
    overdue_count: int
    task_count: int
    email_count: int
    skipped_duplicate_count: int
    error_count: int
    summary_json: dict | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class RecertificationRunDetail(BaseModel):
    run: RecertificationRunRead
    action_logs: list[RecertificationActionLogRead]


class RecertificationSummary(BaseModel):
    active_policies: int
    due_evidence: int
    expired_evidence: int
    evidence_needing_review: int
    due_control_tests: int
    overdue_control_tests: int
    runs_last_24h: int
    tasks_created_last_24h: int
    duplicates_skipped_last_24h: int
