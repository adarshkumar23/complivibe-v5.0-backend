from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.password_validation import PasswordValidationError, validate_password_strength


class OnboardingStartRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=255)
    org_slug: str = Field(min_length=2, max_length=100)
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=255)
    admin_password: str

    @field_validator("admin_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        try:
            return validate_password_strength(value)
        except PasswordValidationError as exc:
            raise ValueError(str(exc)) from exc


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
        try:
            return validate_password_strength(value)
        except PasswordValidationError as exc:
            raise ValueError(str(exc)) from exc


class OnboardingChecklistResponse(BaseModel):
    org_id: uuid.UUID
    onboarding_step: str
    onboarding_completed: bool
    checklist: dict
    checklist_items: list[dict] = Field(default_factory=list)
    completion_percentage: int
    next_step: dict | None = None
    stalled: bool = False
    days_since_created: int = 0
    context_flags: list[str] = Field(default_factory=list)


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


class TV1GitHubIntegrationRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=255)
    token: str = Field(min_length=1, max_length=500)
    api_base_url: str | None = None
    repo_limit: int = Field(default=20, ge=1, le=100)
    target_control_id: uuid.UUID | None = None


class TV1BaselineStartRequest(BaseModel):
    framework_ids: list[uuid.UUID] = Field(default_factory=list)
    github: TV1GitHubIntegrationRequest


class TV1BaselineRunRead(BaseModel):
    run_id: uuid.UUID
    organization_id: uuid.UUID
    status: str
    intake_session_id: uuid.UUID | None = None
    integration_provider: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    gap_report: dict = Field(default_factory=dict)
    context_flags: list[str] = Field(default_factory=list)
    run_age_hours: float | None = None
    is_latest_completed_run: bool = True
    superseded_by_run_id: uuid.UUID | None = None
    obligations_changed_since_generation: bool = False
