from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LEGAL_MATTER_TYPE_PATTERN = "^(litigation|regulatory_inquiry|contract_dispute|ip_dispute|employment|other)$"
LEGAL_MATTER_STATUS_PATTERN = "^(open|in_progress|on_hold|closed)$"
# Status changes must never flow through the generic PATCH update (that would bypass the
# open-linked-issue guard and skip closed_at/closed_by bookkeeping). Only these
# non-terminal statuses are reachable via the dedicated /status transition endpoint;
# "closed" is only reachable via /close, which enforces the confirm guard.
LEGAL_MATTER_TRANSITIONABLE_STATUS_PATTERN = "^(open|in_progress|on_hold)$"


class LegalMatterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    matter_type: str = Field(default="other", pattern=LEGAL_MATTER_TYPE_PATTERN)
    opposing_party: str | None = None
    outside_counsel: str | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    owner_user_id: UUID | None = None
    opened_at: datetime | None = None


class LegalMatterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    matter_type: str | None = Field(default=None, pattern=LEGAL_MATTER_TYPE_PATTERN)
    opposing_party: str | None = None
    outside_counsel: str | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    owner_user_id: UUID | None = None
    opened_at: datetime | None = None


class LegalMatterLinkRiskRequest(BaseModel):
    risk_id: UUID


class LegalMatterLinkIssueRequest(BaseModel):
    issue_id: UUID


class LegalMatterCloseRequest(BaseModel):
    confirm: bool = False


class LegalMatterStatusChangeRequest(BaseModel):
    new_status: str = Field(pattern=LEGAL_MATTER_TRANSITIONABLE_STATUS_PATTERN)


class LegalMatterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    title: str
    description: str | None = None
    matter_type: str = Field(pattern=LEGAL_MATTER_TYPE_PATTERN)
    status: str = Field(pattern=LEGAL_MATTER_STATUS_PATTERN)
    opposing_party: str | None = None
    outside_counsel: str | None = None
    budget: Decimal | None = None
    related_risk_id: UUID | None = None
    related_issue_id: UUID | None = None
    risk_severity_at_link: str | None = None
    owner_user_id: UUID | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    risk_escalated_since_linked: bool = False
    open_linked_issue_warning: str | None = None
