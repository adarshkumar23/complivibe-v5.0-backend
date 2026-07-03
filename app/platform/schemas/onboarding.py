from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class OnboardingStartRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=255)
    org_slug: str = Field(min_length=2, max_length=100)
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=255)
    admin_password: str

    @field_validator("admin_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Password must be at least 10 characters long")
        if re.search(r"[A-Z]", value) is None:
            raise ValueError("Password must include at least one uppercase letter")
        if re.search(r"[a-z]", value) is None:
            raise ValueError("Password must include at least one lowercase letter")
        if re.search(r"\d", value) is None:
            raise ValueError("Password must include at least one number")
        if re.search(r"[^A-Za-z0-9]", value) is None:
            raise ValueError("Password must include at least one symbol")
        return value


class OnboardingStartResponse(BaseModel):
    org_id: uuid.UUID
    org_slug: str
    user_id: uuid.UUID
    access_token: str
    token_type: str = "bearer"
    onboarding_step: str


class FrameworkSelectionRequest(BaseModel):
    framework_ids: list[uuid.UUID] = Field(default_factory=list)


class TeamInviteItem(BaseModel):
    email: EmailStr
    role_code: str = "member"


class TeamInviteRequest(BaseModel):
    invites: list[TeamInviteItem] = Field(default_factory=list)


class AcceptInviteRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=1, max_length=255)
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Password must be at least 10 characters long")
        if re.search(r"[A-Z]", value) is None:
            raise ValueError("Password must include at least one uppercase letter")
        if re.search(r"[a-z]", value) is None:
            raise ValueError("Password must include at least one lowercase letter")
        if re.search(r"\d", value) is None:
            raise ValueError("Password must include at least one number")
        if re.search(r"[^A-Za-z0-9]", value) is None:
            raise ValueError("Password must include at least one symbol")
        return value


class OnboardingChecklistResponse(BaseModel):
    org_id: uuid.UUID
    onboarding_step: str
    onboarding_completed: bool
    checklist: dict
    checklist_items: list[dict] = Field(default_factory=list)
    completion_percentage: int


class TeamInvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role_code: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class TeamInvitationRevokeResponse(BaseModel):
    id: uuid.UUID
    status: str


class TeamInvitationAcceptResponse(BaseModel):
    user_id: uuid.UUID
    org_id: uuid.UUID
    access_token: str
    token_type: str = "bearer"
