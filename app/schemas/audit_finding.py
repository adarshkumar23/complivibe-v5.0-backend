from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

FINDING_SEVERITY_PATTERN = "^(critical|high|medium|low|informational)$"
FINDING_STATUS_PATTERN = "^(open|in_remediation|remediated|closed|accepted_risk)$"


class AuditFindingCreate(BaseModel):
    severity: str = Field(pattern=FINDING_SEVERITY_PATTERN)
    framework_ref: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    assigned_owner_id: UUID
    remediation_action: str = Field(min_length=1)
    target_remediation_date: date
    risk_register_entry_id: UUID | None = None
    control_id: UUID | None = None


class AuditFindingUpdate(BaseModel):
    severity: str | None = Field(default=None, pattern=FINDING_SEVERITY_PATTERN)
    framework_ref: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    assigned_owner_id: UUID | None = None
    remediation_action: str | None = Field(default=None, min_length=1)
    target_remediation_date: date | None = None
    risk_register_entry_id: UUID | None = None
    control_id: UUID | None = None


class AuditFindingTransitionRequest(BaseModel):
    new_status: str = Field(pattern=FINDING_STATUS_PATTERN)


class AuditFindingLinkRiskRequest(BaseModel):
    risk_id: UUID


class AuditFindingBulkTransitionRequest(BaseModel):
    finding_ids: list[UUID] = Field(min_length=1)
    new_status: str = Field(pattern=FINDING_STATUS_PATTERN)


class AuditFindingBulkTransitionResponse(BaseModel):
    updated_count: int
    failed_ids: list[UUID]


class AuditFindingRead(UUIDTimestampSchema):
    organization_id: UUID
    audit_engagement_id: UUID
    finding_ref: str
    severity: str = Field(pattern=FINDING_SEVERITY_PATTERN)
    framework_ref: str | None = None
    title: str
    description: str
    assigned_owner_id: UUID
    remediation_action: str
    target_remediation_date: date
    status: str = Field(pattern=FINDING_STATUS_PATTERN)
    risk_register_entry_id: UUID | None = None
    control_id: UUID | None = None
    control_name: str | None = None
    control_status: str | None = None
    control_archived: bool = False
    scope_changed_since_creation: bool = False
    closed_at: datetime | None = None
    closed_by: UUID | None = None


class AuditFindingSummary(BaseModel):
    total: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    open_critical_count: int
    overdue_count: int
    linked_to_risk_count: int
