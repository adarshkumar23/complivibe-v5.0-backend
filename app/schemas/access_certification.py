from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AccessCertificationItemCreate(BaseModel):
    user_id: UUID
    reviewer_user_id: UUID
    system_key: str = Field(min_length=1, max_length=255)
    system_name: str = Field(min_length=1, max_length=255)
    access_level: str | None = Field(default=None, max_length=255)
    metadata_json: dict | None = None


class AccessCertificationCampaignCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    scope_type: str = Field(default="systems", max_length=64)
    scope_config_json: dict | None = None
    due_date: date | None = None
    status: str = Field(default="draft", pattern="^(draft|active|completed|cancelled|archived)$")
    items: list[AccessCertificationItemCreate] = Field(default_factory=list)


class AccessCertificationCampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    scope_type: str | None = Field(default=None, max_length=64)
    scope_config_json: dict | None = None
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|completed|cancelled|archived)$")


class AccessCertificationDecisionSubmit(BaseModel):
    decision: str = Field(pattern="^(certified|revoked|flagged)$")
    comment: str | None = Field(default=None, max_length=4000)


class AccessCertificationItemRead(BaseModel):
    id: UUID
    organization_id: UUID
    campaign_id: UUID
    user_id: UUID
    reviewer_user_id: UUID
    system_key: str
    system_name: str
    access_level: str | None = None
    status: str
    decision: str | None = None
    decision_comment: str | None = None
    decided_by_user_id: UUID | None = None
    decided_at: datetime | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class AccessCertificationCampaignRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    scope_type: str
    scope_config_json: dict | None = None
    status: str
    due_date: date | None = None
    launched_at: datetime | None = None
    completed_at: datetime | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    total_items: int = 0
    pending_items: int = 0
    certified_items: int = 0
    revoked_items: int = 0
    flagged_items: int = 0


class AccessCertificationCampaignDetail(AccessCertificationCampaignRead):
    items: list[AccessCertificationItemRead] = []
