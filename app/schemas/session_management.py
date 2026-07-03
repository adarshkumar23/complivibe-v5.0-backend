from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    token_id: str
    ip_address: str | None = None
    user_agent: str | None = None
    status: str
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_by: UUID | None = None


class IPAllowlistCreateRequest(BaseModel):
    cidr_range: str
    label: str | None = None


class IPAllowlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    cidr_range: str
    label: str | None = None
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
