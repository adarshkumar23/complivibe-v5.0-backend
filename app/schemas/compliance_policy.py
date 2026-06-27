from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

POLICY_TYPE_PATTERN = "^(acceptable_use|data_retention|incident_response|access_control|change_management|business_continuity|other)$"
POLICY_STATUS_PATTERN = "^(draft|under_review|approved|deprecated|archived)$"


class CompliancePolicyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    policy_type: str = Field(pattern=POLICY_TYPE_PATTERN)
    status: str = Field(default="draft", pattern=POLICY_STATUS_PATTERN)
    owner_user_id: UUID
    effective_date: date | None = None
    review_due_date: date | None = None
    version: str = Field(default="1.0", min_length=1, max_length=32)
    content_url: str | None = Field(default=None, max_length=512)
    tags_json: dict | list | None = None
    notes: str | None = None


class CompliancePolicyUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    policy_type: str | None = Field(default=None, pattern=POLICY_TYPE_PATTERN)
    status: str | None = Field(default=None, pattern=POLICY_STATUS_PATTERN)
    owner_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    effective_date: date | None = None
    review_due_date: date | None = None
    version: str | None = Field(default=None, min_length=1, max_length=32)
    content_url: str | None = Field(default=None, max_length=512)
    tags_json: dict | list | None = None
    notes: str | None = None


class CompliancePolicyArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class CompliancePolicyRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    description: str | None = None
    policy_type: str
    status: str
    owner_user_id: UUID
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    effective_date: date | None = None
    review_due_date: date | None = None
    version: str
    content_url: str | None = None
    tags_json: dict | list | None = None
    notes: str | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    archive_reason: str | None = None
    violation_count: int | None = 0


class CompliancePolicySummary(BaseModel):
    total_policies: int
    by_status: dict[str, int]
    by_policy_type: dict[str, int]


class CompliancePolicyVersionCreate(BaseModel):
    version_number: str = Field(min_length=1, max_length=32)
    content_snapshot_json: dict | list
    change_summary: str | None = None


class CompliancePolicyVersionSubmitRequest(BaseModel):
    notes: str | None = None


class CompliancePolicyVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    version_number: str
    content_snapshot_json: dict | list
    change_summary: str | None = None
    status: str
    submitted_by_user_id: UUID | None = None
    submitted_at: datetime | None = None
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    content_sha256: str
    created_at: datetime


class CompliancePolicyApprovalRequestCreate(BaseModel):
    version_id: UUID
    approver_user_id: UUID
    notes: str | None = None


class CompliancePolicyApprovalRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    version_id: UUID
    requested_by_user_id: UUID
    approver_user_id: UUID
    status: str
    notes: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class CompliancePolicyApprovalDecisionRequest(BaseModel):
    notes: str | None = None
    review_notes: str | None = None


class CompliancePolicyApprovalCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class CompliancePolicyControlLinkCreate(BaseModel):
    control_id: UUID
    link_reason: str | None = None


class CompliancePolicyControlLinkRead(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    control_id: UUID
    link_reason: str | None = None
    status: str
    linked_by_user_id: UUID
    unlinked_at: datetime | None = None
    unlinked_by_user_id: UUID | None = None
    unlink_reason: str | None = None
    created_at: datetime


class CompliancePolicyControlUnlinkRequest(BaseModel):
    unlink_reason: str = Field(min_length=1, max_length=2000)


class CompliancePolicyLinksSummary(BaseModel):
    active_control_links: int
    unlinked_control_links: int
    total_active_links: int
    total_unlinked_links: int
