from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ShareLinkCreate(BaseModel):
    report_type: str
    report_params: dict = Field(default_factory=dict)
    expires_hours: int = Field(default=168, ge=1, le=24 * 365)
    password: str | None = None
    max_views: int | None = Field(default=None, ge=1, le=100000)
    recipient_email: EmailStr | None = None
    watermark_text: str | None = None


class ShareLinkResponse(BaseModel):
    share_id: uuid.UUID
    share_url: str
    token: str
    expires_at: datetime
    password_protected: bool
    max_views: int | None
    watermark_text: str | None
    expires_in_hours: float
    context_flags: list[str] = Field(default_factory=list)
    warning: str


class ShareLinkListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: str
    expires_at: datetime
    view_count: int
    max_views: int | None
    views_remaining: int | None = None
    is_active: bool
    is_expired: bool = False
    is_locked: bool = False
    password_protected: bool = False
    expires_in_hours: float
    context_flags: list[str] = Field(default_factory=list)
    recipient_email: str | None
    created_at: datetime


class SharePasswordVerifyRequest(BaseModel):
    password: str | None = None


class SharePasswordVerifyResponse(BaseModel):
    valid: bool
