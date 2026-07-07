from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

VENDOR_RISK_AXIS_PATTERN = "^(very_low|low|medium|high|very_high)$"
VENDOR_RISK_LEVEL_PATTERN = "^(critical|high|medium|low|not_assessed)$"


class VendorRiskScoreCreate(BaseModel):
    assessment_id: UUID | None = None
    likelihood: str = Field(pattern=VENDOR_RISK_AXIS_PATTERN)
    impact: str = Field(pattern=VENDOR_RISK_AXIS_PATTERN)
    notes: str | None = None


class VendorRiskScoreRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID
    assessment_id: UUID | None = None
    likelihood: str
    impact: str
    inherent_risk_score: int
    risk_level: str
    score_explanation_json: dict | list
    scored_by_user_id: UUID
    notes: str | None = None
    created_at: datetime
    recalculated_since_update: bool = False
    stale_reason: str | None = None


class VendorControlLinkCreate(BaseModel):
    control_id: UUID
    link_reason: str | None = None


class VendorControlLinkRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID
    control_id: UUID
    link_reason: str | None = None
    status: str
    linked_by_user_id: UUID
    unlinked_at: datetime | None = None
    unlinked_by_user_id: UUID | None = None
    unlink_reason: str | None = None
    created_at: datetime


class VendorControlUnlinkRequest(BaseModel):
    unlink_reason: str = Field(min_length=1, max_length=2000)


class VendorLinksSummary(BaseModel):
    active_control_links: int
    unlinked_control_links: int
    total_active_links: int
    total_unlinked_links: int
