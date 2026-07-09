from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AttestationCampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    policy_id: UUID
    policy_version: str = Field(min_length=1, max_length=50)
    due_date: date
    attestation_expiry_days: int = Field(default=365, ge=1, le=3650)
    user_ids: list[UUID] = Field(default_factory=list, min_length=1)


class AttestationCampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    due_date: date | None = None


class AttestationCampaignResponse(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    policy_version: str
    name: str
    description: str | None = None
    due_date: date
    attestation_expiry_days: int
    status: str = Field(pattern="^(active|completed|cancelled)$")
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    total_assigned: int
    attested_count: int
    declined_count: int = 0
    pending_count: int
    expired_count: int
    exempted_count: int
    completion_rate: float
    policy_changed_since_campaign_start: bool = False
    current_policy_version: str | None = None


class AttestationCampaignCreateResponse(BaseModel):
    campaign: AttestationCampaignResponse
    record_count_created: int


class AttestationCampaignRef(BaseModel):
    id: UUID
    name: str
    policy_id: UUID
    policy_name: str | None = None
    policy_version: str
    due_date: date
    status: str = Field(pattern="^(active|completed|cancelled)$")


class AttestationRecordResponse(BaseModel):
    id: UUID
    organization_id: UUID
    campaign_id: UUID
    user_id: UUID
    status: str = Field(pattern="^(pending|attested|expired|exempted)$")
    attested_at: datetime | None = None
    expires_at: datetime | None = None
    exemption_reason: str | None = None
    reminder_sent_at: datetime | None = None
    created_at: datetime
    campaign: AttestationCampaignRef


class AttestationUserBreakdownResponse(BaseModel):
    user_id: UUID
    name: str
    email: str
    status: str = Field(pattern="^(pending|attested|expired|exempted)$")
    attested_at: datetime | None = None
    expires_at: datetime | None = None
    reminder_sent_at: datetime | None = None
    days_overdue: int | None = None


class AttestationDashboardResponse(BaseModel):
    active_campaigns: int
    overdue_campaigns: int
    overall_completion_rate: float
    pending_attestations_count: int
    campaigns_expiring_soon: list[AttestationCampaignResponse]


class PolicyAttestationSummaryResponse(BaseModel):
    policy_id: UUID
    overall_completion_rate: float
    campaigns_count: int
    most_recent_campaign_id: UUID | None = None
    overdue_count: int


class AttestationExemptionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class AttestationReminderResponse(BaseModel):
    reminders_queued: int
