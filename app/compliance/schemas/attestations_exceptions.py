from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AttestationCampaignCreateRequest(BaseModel):
    policy_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    due_date: date
    attestation_text: str | None = None
    policy_version_id: UUID | None = None


class AttestationCampaignResponse(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    policy_version_id: UUID | None = None
    title: str
    description: str | None = None
    attestation_text_shown: str
    content_hash: str
    due_date: date
    status: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AttestationSummaryResponse(BaseModel):
    campaign: AttestationCampaignResponse
    total_members: int
    attested_count: int
    declined_count: int
    pending_count: int
    completion_pct: float
    policy_changed_since_campaign_start: bool = False
    current_policy_version: str | None = None


class AttestationRecordResponse(BaseModel):
    id: UUID
    organization_id: UUID
    campaign_id: UUID
    user_id: UUID
    status: str
    attested_at: datetime | None = None
    declined_at: datetime | None = None
    decline_reason: str | None = None
    ip_address: str | None = None
    created_at: datetime
    updated_at: datetime


class AttestationDeclineRequest(BaseModel):
    decline_reason: str | None = None


class PolicyExceptionCreateRequest(BaseModel):
    policy_id: UUID
    reason: str = Field(min_length=1)
    compensating_measure_description: str | None = None


class PolicyExceptionApproveRequest(BaseModel):
    expiry_date: date


class PolicyExceptionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    reason: str | None = None
    requested_by: UUID
    approved_by: UUID | None = None
    rejected_by: UUID | None = None
    status: str
    compensating_measure_description: str | None = None
    expiry_date: date | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    expired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    policy_is_archived: bool = False
    policy_current_version: str | None = None


class PolicyExceptionSnoozeResponse(BaseModel):
    expired_count: int
