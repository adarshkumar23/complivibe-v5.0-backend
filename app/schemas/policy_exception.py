from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


STATUS_PATTERN = "^(pending|approved|rejected|expired|withdrawn)$"
RISK_LEVEL_PATTERN = "^(low|medium|high|critical)$"
DECISION_PATTERN = "^(approved|rejected)$"


class PolicyExceptionCreate(BaseModel):
    policy_id: UUID
    policy_version: str | None = Field(default=None, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    compensating_measure: str | None = None
    requestor_scope: str | None = Field(default=None, max_length=255)
    requested_expiry_date: date
    risk_level: str = Field(default="medium", pattern=RISK_LEVEL_PATTERN)


class PolicyExceptionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    justification: str | None = Field(default=None, min_length=1)
    compensating_measure: str | None = None
    requestor_scope: str | None = Field(default=None, max_length=255)
    requested_expiry_date: date | None = None
    risk_level: str | None = Field(default=None, pattern=RISK_LEVEL_PATTERN)


class PolicyExceptionApprovalCreate(BaseModel):
    decision_reason: str = Field(min_length=1)
    approved_expiry_date: date
    conditions: str | None = None


class PolicyExceptionRejectionCreate(BaseModel):
    decision_reason: str = Field(min_length=1)


class PolicyExceptionApprovalResponse(BaseModel):
    id: UUID
    exception_id: UUID
    reviewed_by: UUID
    decision: str = Field(pattern=DECISION_PATTERN)
    decision_reason: str
    approved_expiry_date: date | None = None
    conditions: str | None = None
    reviewed_at: datetime


class PolicyRef(BaseModel):
    id: UUID
    name: str
    status: str | None = None
    current_version: str | None = None


class PolicyExceptionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    policy_version: str | None = None
    title: str
    description: str
    justification: str
    compensating_measure: str | None = None
    requestor_scope: str | None = None
    requested_by: UUID
    requested_expiry_date: date
    status: str = Field(pattern=STATUS_PATTERN)
    approved_expiry_date: date | None = None
    risk_level: str = Field(pattern=RISK_LEVEL_PATTERN)
    created_at: datetime
    updated_at: datetime
    approval: PolicyExceptionApprovalResponse | None = None
    policy: PolicyRef
    policy_version_is_stale: bool = False


class PolicyExceptionSummaryResponse(BaseModel):
    policy_id: UUID
    active_exceptions: int
    pending_count: int
    historical_count: int
    avg_exception_duration_days: float | None = None
    most_common_risk_level: str | None = None


class PolicyExceptionDashboardResponse(BaseModel):
    total_pending: int
    total_active: int
    expiring_soon: list[PolicyExceptionResponse]
    high_risk_active: list[PolicyExceptionResponse]
    overdue_pending: list[PolicyExceptionResponse]
