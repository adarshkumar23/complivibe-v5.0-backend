import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PrivacyNoticeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    language: str = Field(default="en", max_length=10)
    effective_date: date | None = None
    frameworks: list[str] = Field(default_factory=list)


class PrivacyNoticeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None
    language: str | None = Field(default=None, max_length=10)
    effective_date: date | None = None
    frameworks: list[str] | None = None


class PrivacyNoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    version: str
    content: str
    content_hash: str
    language: str
    status: str
    published_at: datetime | None
    published_by: uuid.UUID | None
    effective_date: date | None
    frameworks: list
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class NoticeAcknowledgementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    notice_id: uuid.UUID
    user_id: uuid.UUID
    acknowledged_at: datetime
    ip_address: str | None
    user_agent: str | None


class NoticeAcknowledgementStatus(BaseModel):
    total_users: int
    acknowledged_count: int
    pending_count: int
    acknowledgement_rate_pct: float
