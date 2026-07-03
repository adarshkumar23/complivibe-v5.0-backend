from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

ISSUE_TYPE_PATTERN = "^(security_incident|compliance_violation|operational_failure|vendor_failure|data_loss|unauthorized_access|policy_violation|custom)$"
ISSUE_SEVERITY_PATTERN = "^(critical|high|medium|low)$"
# Must stay in sync with the ``ck_issues_source_type`` CHECK constraint on the
# ``issues`` table (app/models/issue.py + alembic 0136). Internal escalation paths
# (e.g. data-incident auto-issues) write the model directly, so IssueRead must be
# able to serialize every value the DB permits — otherwise listing issues 500s.
ISSUE_SOURCE_TYPES = (
    "manual",
    "monitoring_alert",
    "audit_finding",
    "vendor_assessment",
    "external_report",
    "data_incident",
    "risk_assessment",
)
ISSUE_SOURCE_TYPE_PATTERN = "^(" + "|".join(ISSUE_SOURCE_TYPES) + ")$"
ISSUE_STATUS_PATTERN = "^(open|investigating|mitigating|resolved|closed)$"


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    issue_type: str = Field(pattern=ISSUE_TYPE_PATTERN)
    severity: str = Field(pattern=ISSUE_SEVERITY_PATTERN)
    source_type: str = Field(default="manual", pattern=ISSUE_SOURCE_TYPE_PATTERN)
    source_id: UUID | None = None
    owner_id: UUID
    assigned_to: UUID | None = None


class IssuePromoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    issue_type: str = Field(pattern=ISSUE_TYPE_PATTERN)
    severity: str = Field(pattern=ISSUE_SEVERITY_PATTERN)
    owner_id: UUID
    assigned_to: UUID | None = None


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    owner_id: UUID | None = None
    assigned_to: UUID | None = None


class IssueAssignRequest(BaseModel):
    assigned_to: UUID


class IssueTransitionRequest(BaseModel):
    new_status: str = Field(pattern=ISSUE_STATUS_PATTERN)
    notes: str | None = None
    resolution_note: str | None = None


class IssueRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: str
    issue_type: str = Field(pattern=ISSUE_TYPE_PATTERN)
    severity: str = Field(pattern=ISSUE_SEVERITY_PATTERN)
    source_type: str = Field(pattern=ISSUE_SOURCE_TYPE_PATTERN)
    source_id: UUID | None = None
    status: str = Field(pattern=ISSUE_STATUS_PATTERN)
    owner_id: UUID
    assigned_to: UUID | None = None
    created_by: UUID
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class IssueTransitionRead(BaseModel):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    from_status: str = Field(pattern=ISSUE_STATUS_PATTERN)
    to_status: str = Field(pattern=ISSUE_STATUS_PATTERN)
    actor_id: UUID
    notes: str | None = None
    transitioned_at: datetime


class IssueDashboard(BaseModel):
    total: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    by_type: dict[str, int]
    open_critical_count: int
    avg_time_to_resolve_hours: float
    unassigned_count: int
    overdue_count: int
