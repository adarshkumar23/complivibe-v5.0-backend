from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

FINDING_SEVERITIES = ("critical", "high", "medium", "low", "informational")
FINDING_TYPES = ("observation", "minor_nonconformity", "major_nonconformity", "opportunity_for_improvement")


class PBCRequestItemCreate(BaseModel):
    item_description: str = Field(min_length=1)
    assigned_to: UUID | None = None
    due_date: date | None = None


class PBCBulkCreateRequest(BaseModel):
    items: list[PBCRequestItemCreate] = Field(min_length=1)


class PBCSubmitRequest(BaseModel):
    evidence_id: UUID | None = None


class PBCRejectRequest(BaseModel):
    rejection_reason: str | None = None


class PBCRequestResponse(BaseModel):
    id: UUID
    organization_id: UUID
    audit_id: UUID
    item_description: str
    assigned_to: UUID | None = None
    status: str
    due_date: date | None = None
    evidence_id: UUID | None = None
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class AuditFindingCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    severity: Literal[FINDING_SEVERITIES]
    finding_type: Literal[FINDING_TYPES]
    control_id: UUID | None = None
    remediation_plan: str | None = None
    remediation_due_date: date | None = None
    remediation_owner_id: UUID | None = None


class AuditFindingRemediationUpdateRequest(BaseModel):
    remediation_plan: str | None = None
    remediation_due_date: date | None = None
    remediation_owner_id: UUID | None = None


class AuditFindingResponse(BaseModel):
    id: UUID
    organization_id: UUID
    audit_id: UUID
    control_id: UUID | None = None
    title: str
    description: str
    severity: str
    finding_type: str
    status: str
    remediation_plan: str | None = None
    remediation_due_date: date | None = None
    remediation_owner_id: UUID | None = None
    linked_risk_id: UUID | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PBCBulkCreateResponse(BaseModel):
    items: list[PBCRequestResponse]
    count: int
