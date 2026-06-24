from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

EXCEPTION_TYPE_PATTERN = "^(temporary|permanent|conditional)$"
EXCEPTION_STATUS_PATTERN = "^(pending_approval|approved|rejected|active|expired|revoked|cancelled)$"
APPROVAL_STATUS_PATTERN = "^(pending|approved|rejected|skipped)$"


class ControlExceptionApprovalStepCreate(BaseModel):
    user_id: UUID
    sequence: int = Field(default=1, ge=1, le=32767)


class ControlExceptionApprovalStepRead(BaseModel):
    id: UUID
    organization_id: UUID
    exception_id: UUID
    approver_user_id: UUID
    sequence: int
    status: str = Field(pattern=APPROVAL_STATUS_PATTERN)
    decision_notes: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class ControlExceptionCreate(BaseModel):
    control_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    exception_type: str = Field(pattern=EXCEPTION_TYPE_PATTERN)
    risk_acceptance_reason: str = Field(min_length=1)
    compensating_control_id: UUID | None = None
    compensating_description: str | None = None
    owner_user_id: UUID
    effective_date: date
    expiry_date: date | None = None
    review_date: date | None = None
    approvers: list[ControlExceptionApprovalStepCreate] | None = None
    tags_json: dict | list | None = None
    notes: str | None = None


class ControlExceptionRead(UUIDTimestampSchema):
    organization_id: UUID
    control_id: UUID
    title: str
    description: str
    exception_type: str
    risk_acceptance_reason: str
    compensating_control_id: UUID | None = None
    compensating_description: str | None = None
    requested_by_user_id: UUID
    owner_user_id: UUID
    status: str = Field(pattern=EXCEPTION_STATUS_PATTERN)
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    revoked_by_user_id: UUID | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    effective_date: date
    expiry_date: date | None = None
    review_date: date | None = None
    auto_expired_at: datetime | None = None
    tags_json: dict | list | None = None
    notes: str | None = None


class ControlExceptionDetail(ControlExceptionRead):
    approvals: list[ControlExceptionApprovalStepRead]


class ControlExceptionSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    expiring_soon: int
    expired_unreviewed: int
    controls_with_active_exception: int


class ControlExceptionApproveRequest(BaseModel):
    decision_notes: str | None = None


class ControlExceptionRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=4000)


class ControlExceptionRevokeRequest(BaseModel):
    revocation_reason: str = Field(min_length=1, max_length=4000)


class ControlExceptionExpiryCheckResponse(BaseModel):
    expired_count: int
    expired_exceptions: list[ControlExceptionRead]
