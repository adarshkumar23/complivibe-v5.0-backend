from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ActivationTokenCreateResponse(BaseModel):
    membership_id: UUID
    user_id: UUID
    expires_at: datetime
    activation_token: str
    warning: str


class ActivateInviteRequest(BaseModel):
    activation_token: str = Field(min_length=32)
    password: str
    full_name: str | None = None


class ActivateInviteResponse(BaseModel):
    message: str


class ActivationTokenStatusResponse(BaseModel):
    membership_id: UUID
    has_active_token: bool
    status: str | None = None
    expires_at: datetime | None = None


class ActivationTokenRevokeResponse(BaseModel):
    membership_id: UUID
    revoked_count: int
    detail: str
