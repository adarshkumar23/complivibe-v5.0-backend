from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import UUIDTimestampSchema

EXCEPTION_TYPE_PATTERN = "^(temporary|permanent|conditional)$"
EXCEPTION_STATUS_PATTERN = "^(pending_approval|approved|rejected|active|expired|revoked|cancelled)$"
APPROVAL_STATUS_PATTERN = "^(pending|approved|rejected|skipped)$"


class ControlExceptionApprovalStepCreate(BaseModel):
    user_id: UUID = Field(description="An active member of the organization who must approve this exception.")
    sequence: int = Field(default=1, ge=1, le=32767, description="Approval order; lower sequence numbers approve first. Must be unique within a single request.")


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
    control_id: UUID = Field(description="The control this exception applies to. Must belong to the caller's organization.")
    title: str = Field(min_length=1, max_length=255, description="Short, human-readable title for the exception.")
    description: str = Field(min_length=1, description="Full description of what the exception covers and why it's needed.")
    exception_type: str = Field(
        pattern=EXCEPTION_TYPE_PATTERN,
        description=(
            "One of 'temporary', 'permanent', or 'conditional'. This determines whether "
            "expiry_date is required: 'temporary' and 'conditional' exceptions REQUIRE "
            "expiry_date; 'permanent' exceptions must NOT set expiry_date."
        ),
    )
    risk_acceptance_reason: str = Field(
        min_length=1,
        description="Required justification for why the residual risk of this exception is being formally accepted.",
    )
    compensating_control_id: UUID | None = Field(
        default=None,
        description="Optional: an alternate control (in the same organization) that partially mitigates the risk this exception creates.",
    )
    compensating_description: str | None = Field(
        default=None,
        description="Optional free-text description of any compensating measures in place, independent of compensating_control_id.",
    )
    owner_user_id: UUID = Field(description="Required: an active member of the organization accountable for this exception.")
    effective_date: date = Field(description="Required: the date this exception takes effect.")
    expiry_date: date | None = Field(
        default=None,
        description=(
            "Required (and must be strictly after effective_date) when exception_type is "
            "'temporary' or 'conditional'. Must be omitted when exception_type is 'permanent'."
        ),
    )
    review_date: date | None = Field(default=None, description="Optional date by which this exception should be re-reviewed.")
    approvers: list[ControlExceptionApprovalStepCreate] | None = Field(
        default=None,
        description="Optional ordered list of required approvers. Each user_id must be an active org member; sequence values must be unique.",
    )
    tags_json: dict | list | None = Field(default=None, description="Optional free-form tags/labels for categorization.")
    notes: str | None = Field(default=None, description="Optional free-text internal notes.")

    @model_validator(mode="after")
    def _validate_expiry_rules(self) -> "ControlExceptionCreate":
        """Cross-field rules that determine whether expiry_date is actually required.

        Previously enforced only in application code (ControlExceptionService.
        _validate_expiry_rules), which meant these real requirements never showed up
        in the OpenAPI schema/generated docs -- callers only discovered them via 422
        trial-and-error. Moving them into the schema makes FastAPI's own request
        validation reject bad payloads before the service is ever called, and lets
        OpenAPI/generated client docs describe the actual rules (see field
        descriptions on exception_type/expiry_date above).
        """
        if self.exception_type == "permanent" and self.expiry_date is not None:
            raise ValueError("permanent exceptions must not include expiry_date")
        if self.exception_type in {"temporary", "conditional"} and self.expiry_date is None:
            raise ValueError(f"{self.exception_type} exceptions require expiry_date")
        if self.expiry_date is not None and self.expiry_date <= self.effective_date:
            raise ValueError("expiry_date must be greater than effective_date")
        return self


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
    review_overdue: bool = False


class ControlExceptionDetail(ControlExceptionRead):
    approvals: list[ControlExceptionApprovalStepRead]


class ControlExceptionSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    expiring_soon: int
    expired_unreviewed: int
    controls_with_active_exception: int
    review_overdue: int


class ControlExceptionApproveRequest(BaseModel):
    decision_notes: str | None = None


class ControlExceptionRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=4000)


class ControlExceptionRevokeRequest(BaseModel):
    revocation_reason: str = Field(min_length=1, max_length=4000)


class ControlExceptionExpiryCheckResponse(BaseModel):
    expired_count: int
    expired_exceptions: list[ControlExceptionRead]
