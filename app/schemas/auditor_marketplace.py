from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class AuditorRead(UUIDTimestampSchema):
    name: str
    email: str
    firm: str
    certifications_json: list[str]
    frameworks_json: list[str]
    rate_usd_per_day: float
    availability: str
    verified: bool
    bio: str | None = None
    status: str


class AuditorEngagementCreate(BaseModel):
    auditor_id: UUID
    framework_id: UUID
    start_date: datetime
    end_date: datetime
    title: str = Field(min_length=1, max_length=255)
    revenue_share_fee_pct: float = Field(default=12.0, ge=10.0, le=15.0)
    invite_days_valid: int = Field(default=30, ge=1, le=90)
    notes: str | None = None


class AuditorEngagementRead(UUIDTimestampSchema):
    organization_id: UUID
    auditor_id: UUID
    audit_engagement_id: UUID
    framework: str
    status: str
    started_at: datetime
    revenue_share_fee_pct: float
    notes: str | None = None
    created_by: UUID


class AuditorEngagementCreateResponse(BaseModel):
    engagement: AuditorEngagementRead
    portal_invitation_id: UUID
    portal_token: str
