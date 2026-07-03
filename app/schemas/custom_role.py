from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CustomRoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permission_codes: list[str] = Field(default_factory=list)


class CustomRoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    permission_codes: list[str] | None = None


class AssignRoleRequest(BaseModel):
    role_id: UUID


class CustomRoleRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    name: str
    description: str | None = None
    is_system_role: bool
    is_active: bool
    permission_codes: list[str]
    created_at: datetime
    updated_at: datetime
