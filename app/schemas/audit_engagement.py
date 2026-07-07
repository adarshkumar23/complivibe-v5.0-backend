from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

AUDIT_TYPE_PATTERN = "^(internal_readiness|external_certification|surveillance|gap_assessment)$"
AUDIT_STATUS_PATTERN = "^(planning|fieldwork|review|report_issuance|closed|cancelled)$"


class AuditEngagementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    audit_type: str = Field(pattern=AUDIT_TYPE_PATTERN)
    scope_framework_ids: list[UUID] = Field(default_factory=list)
    assigned_auditor_ids: list[UUID] = Field(default_factory=list)
    start_date: date
    end_date: date
    lead_auditor_name: str | None = Field(default=None, max_length=255)
    audit_firm: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class AuditEngagementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    audit_type: str | None = Field(default=None, pattern=AUDIT_TYPE_PATTERN)
    scope_framework_ids: list[UUID] | None = None
    assigned_auditor_ids: list[UUID] | None = None
    start_date: date | None = None
    end_date: date | None = None
    lead_auditor_name: str | None = Field(default=None, max_length=255)
    audit_firm: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class AuditEngagementTransitionRequest(BaseModel):
    new_status: str = Field(pattern=AUDIT_STATUS_PATTERN)


class AuditEngagementRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    audit_type: str = Field(pattern=AUDIT_TYPE_PATTERN)
    scope_framework_ids: list[UUID]
    assigned_auditor_ids: list[UUID]
    status: str = Field(pattern=AUDIT_STATUS_PATTERN)
    start_date: date
    end_date: date
    report_issued_at: datetime | None = None
    lead_auditor_name: str | None = None
    audit_firm: str | None = None
    notes: str | None = None
    created_by: UUID


class AuditEngagementDashboard(BaseModel):
    total_engagements: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    upcoming: int
    overdue: int


class AuditEngagementScopeImpact(BaseModel):
    engagement_id: UUID
    current_scope_framework_ids: list[UUID]
    findings_total: int
    findings_created_under_stale_scope: int
    evidence_packages_total: int
    evidence_packages_created_under_stale_scope: int
