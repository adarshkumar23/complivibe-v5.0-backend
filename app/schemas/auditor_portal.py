from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import AppBaseSchema

PORTAL_INVITATION_STATUS_PATTERN = "^(active|revoked|expired)$"


class AuditorPortalInvitationCreate(BaseModel):
    auditor_email: EmailStr
    auditor_name: str | None = Field(default=None, max_length=255)
    scoped_framework_ids: list[UUID] = Field(default_factory=list)
    scoped_control_ids: list[UUID] | None = None
    scoped_evidence_ids: list[UUID] | None = None
    expires_in_days: int = Field(default=30, ge=1, le=90)


class AuditorPortalInvitationCreateResponse(BaseModel):
    invitation_id: UUID
    auditor_email: EmailStr
    framework_id: UUID | None = None
    expires_at: datetime
    plaintext_token: str
    warning: str


class AuditorPortalInvitationRead(AppBaseSchema):
    id: UUID
    organization_id: UUID
    audit_engagement_id: UUID
    auditor_email: EmailStr
    auditor_name: str | None = None
    masked_email: str
    framework_id: UUID | None = None
    scoped_framework_ids: list[UUID]
    scoped_control_ids: list[UUID] | None = None
    scoped_evidence_ids: list[UUID] | None = None
    expires_at: datetime
    first_accessed_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int
    status: str = Field(pattern=PORTAL_INVITATION_STATUS_PATTERN)
    revoked_at: datetime | None = None
    revoked_by: UUID | None = None
    created_by: UUID
    created_at: datetime


class AuditorPortalRevokeResponse(BaseModel):
    invitation_id: UUID
    status: str = Field(pattern=PORTAL_INVITATION_STATUS_PATTERN)


class AuditorPortalMeResponse(BaseModel):
    auditor_email: EmailStr
    audit_engagement_title: str
    expires_at: datetime
    scoped_framework_ids: list[UUID]
    access_count: int


class AuditorPortalControlRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    framework_id: UUID | None = None
    status: str


class AuditorPortalEvidenceRead(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    status: str
    submitted_at: datetime | None = None
    file_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    storage_provider: str | None = None
    storage_key: str | None = None


class AuditorPortalReportRead(BaseModel):
    id: UUID
    report_type: str
    title: str
    description: str | None = None
    status: str
    framework_id: UUID | None = None
    generated_at: datetime
