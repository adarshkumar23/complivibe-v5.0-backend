from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

FINDING_SEVERITY_PATTERN = "^(critical|high|medium|low|informational)$"

# Single source of truth for every status value any writer of AuditFinding.status may
# persist -- both the v1 surface (app/api/v1/audit_findings.py, whose ALLOWED_TRANSITIONS
# in AuditFindingService produces open/in_remediation/remediated/closed/accepted_risk) and
# the v2 "pbc" surface (app/compliance/routers/audit_findings.py, whose service methods
# produce remediation_in_progress/resolved/accepted_risk/closed) share the SAME
# audit_findings table and the SAME `status` column. AuditFindingRead (used only by the
# v1 list/detail endpoints) validates `status` against FINDING_STATUS_PATTERN; if either
# surface ever writes a value the other doesn't know about, serializing ANY finding in the
# org through the v1 endpoints raises a pydantic ValidationError and 500s the whole list
# -- not just the one row. This must stay a superset of BOTH surfaces' vocabularies (and
# of the DB's ck_audit_findings_status CHECK constraint) so that can never happen again,
# regardless of which router/service wrote the row. "risk_accepted" is a legacy alias
# retained only so old rows (written before accepted_risk was standardized) keep
# deserializing; no code path writes it going forward.
FINDING_STATUSES: tuple[str, ...] = (
    "open",
    "in_remediation",
    "remediation_in_progress",
    "remediated",
    "resolved",
    "accepted_risk",
    "risk_accepted",
    "closed",
)
FINDING_STATUS_PATTERN = "^(" + "|".join(FINDING_STATUSES) + ")$"


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
