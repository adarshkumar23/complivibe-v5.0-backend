from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class MembershipUserRead(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None = None
    status: str
    is_active: bool


class MembershipRead(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str
    status: str
    invited_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    user: MembershipUserRead


class MembershipCreate(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role_id: UUID | None = None
    role_name: str | None = None
    status: str | None = Field(default=None, pattern="^(invited|active)$")


class MembershipRoleUpdate(BaseModel):
    role_id: UUID | None = None
    role_name: str | None = None


class MembershipDeactivateResponse(BaseModel):
    membership_id: UUID
    status: str
    detail: str
    # Result of the non-human-identity orphan scan run as part of this deactivation
    # (see NonHumanIdentityService.flag_orphaned_identities) -- surfaced so callers/
    # auditors can see that offboarding actually triggered orphan detection instead of
    # leaving it to a separate, easy-to-forget manual scan.
    non_human_identities_scanned: int = 0
    non_human_identities_orphaned_flagged: int = 0
