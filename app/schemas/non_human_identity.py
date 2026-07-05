from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

IDENTITY_TYPE_PATTERN = "^(service_account|api_key|bot)$"
IDENTITY_STATUS_PATTERN = "^(active|inactive|orphaned|deleted)$"
RISK_LEVEL_PATTERN = "^(low|medium|high|critical)$"


class NonHumanIdentityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    identity_type: str = Field(pattern=IDENTITY_TYPE_PATTERN)
    owner_user_id: UUID
    permissions_scope: str | None = Field(default=None, max_length=4000)
    external_ref: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=64)
    last_used_at: datetime | None = None
    rotation_due_at: datetime | None = None
    last_rotated_at: datetime | None = None
    status: str = Field(default="active", pattern=IDENTITY_STATUS_PATTERN)
    is_active: bool = True
    risk_level: str = Field(default="low", pattern=RISK_LEVEL_PATTERN)
    risk_reason: str | None = Field(default=None, max_length=4000)


class NonHumanIdentityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    identity_type: str | None = Field(default=None, pattern=IDENTITY_TYPE_PATTERN)
    owner_user_id: UUID | None = None
    permissions_scope: str | None = Field(default=None, max_length=4000)
    external_ref: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=64)
    last_used_at: datetime | None = None
    rotation_due_at: datetime | None = None
    last_rotated_at: datetime | None = None
    status: str | None = Field(default=None, pattern=IDENTITY_STATUS_PATTERN)
    is_active: bool | None = None
    risk_level: str | None = Field(default=None, pattern=RISK_LEVEL_PATTERN)
    risk_reason: str | None = Field(default=None, max_length=4000)


class NonHumanIdentityRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    identity_type: str
    owner_user_id: UUID
    permissions_scope: str | None = None
    external_ref: str | None = None
    environment: str | None = None
    last_used_at: datetime | None = None
    rotation_due_at: datetime | None = None
    last_rotated_at: datetime | None = None
    status: str
    is_active: bool
    is_orphaned: bool
    orphan_detected_at: datetime | None = None
    risk_level: str
    risk_reason: str | None = None
    created_by_user_id: UUID
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None


class NonHumanIdentitySummary(BaseModel):
    total_identities: int
    active_identities: int
    inactive_identities: int
    stale_identities: int
    unrotated_identities: int
    orphaned_identities: int
    high_risk_identities: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    by_risk_level: dict[str, int]


class NonHumanIdentityOrphanScanResponse(BaseModel):
    identities_scanned: int
    orphaned_flagged: int
    already_orphaned: int
