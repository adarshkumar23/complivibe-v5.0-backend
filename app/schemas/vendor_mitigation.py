from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

VENDOR_MITIGATION_CASE_SEVERITY_PATTERN = "^(critical|high|medium|low)$"
VENDOR_MITIGATION_CASE_STATUS_PATTERN = "^(open|in_progress|pending_vendor_evidence|under_review|closed|escalated|cancelled)$"
VENDOR_MITIGATION_ACTION_TYPE_PATTERN = "^(policy_update|technical_control|training|documentation|audit|contract_amendment|custom)$"
VENDOR_MITIGATION_ACTION_STATUS_PATTERN = "^(open|in_progress|evidence_submitted|accepted|rejected|overdue)$"


class VendorMitigationCaseCreate(BaseModel):
    vendor_id: UUID
    assessment_id: UUID | None = None
    ai_assessment_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    severity: str = Field(pattern=VENDOR_MITIGATION_CASE_SEVERITY_PATTERN)
    assigned_owner_id: UUID
    due_date: date


class VendorMitigationCaseTransitionRequest(BaseModel):
    new_status: str = Field(pattern=VENDOR_MITIGATION_CASE_STATUS_PATTERN)
    notes: str | None = None


class VendorMitigationCaseEscalateRequest(BaseModel):
    reason: str = Field(min_length=1)


class VendorMitigationActionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    action_type: str = Field(pattern=VENDOR_MITIGATION_ACTION_TYPE_PATTERN)
    assigned_to_vendor: bool = False
    due_date: date


class VendorMitigationActionEvidenceSubmitRequest(BaseModel):
    evidence_id: UUID


class VendorMitigationActionRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class VendorMitigationCaseRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID
    assessment_id: UUID | None = None
    ai_assessment_id: UUID | None = None
    title: str
    description: str
    severity: str = Field(pattern=VENDOR_MITIGATION_CASE_SEVERITY_PATTERN)
    status: str = Field(pattern=VENDOR_MITIGATION_CASE_STATUS_PATTERN)
    assigned_owner_id: UUID
    due_date: date
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    closure_notes: str | None = None
    escalated_at: datetime | None = None
    escalated_by: UUID | None = None
    escalation_reason: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class VendorMitigationActionRead(BaseModel):
    id: UUID
    organization_id: UUID
    case_id: UUID
    title: str
    description: str
    action_type: str = Field(pattern=VENDOR_MITIGATION_ACTION_TYPE_PATTERN)
    assigned_to_vendor: bool
    due_date: date
    status: str = Field(pattern=VENDOR_MITIGATION_ACTION_STATUS_PATTERN)
    evidence_id: UUID | None = None
    evidence_submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    accepted_by: UUID | None = None
    rejected_at: datetime | None = None
    rejected_by: UUID | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class VendorMitigationSummary(BaseModel):
    total_cases: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    open_critical_count: int
    overdue_cases: int
    avg_days_to_close: float
    pending_evidence_count: int
    total_actions: int
    actions_by_status: dict[str, int]
