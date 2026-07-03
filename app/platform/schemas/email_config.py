from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class EmailConfigUpsertRequest(BaseModel):
    use_platform_ses: bool = True
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = "ap-south-1"
    from_email: EmailStr | None = None
    from_name: str | None = None
    reply_to_email: EmailStr | None = None
    daily_send_limit: int = Field(default=1000, ge=1, le=100000)


class EmailConfigResponse(BaseModel):
    id: uuid.UUID | None = None
    organization_id: uuid.UUID
    use_platform_ses: bool
    aws_region: str | None
    from_email: str | None
    from_name: str | None
    reply_to_email: str | None
    is_active: bool
    sent_today: int
    daily_send_limit: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmailConfigTestResponse(BaseModel):
    success: bool
    message_id: str | None = None
    sent_to: str


class EmailSenderVerificationResponse(BaseModel):
    valid: bool
    sender_verified: bool | None = None
    email_verification_status: str | None = None
    max_24h_send: float | int | None = None
    sent_last_24h: float | int | None = None
    error: str | None = None
