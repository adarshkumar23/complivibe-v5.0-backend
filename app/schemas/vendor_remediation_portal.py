from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.vendor_mitigation import (
    VENDOR_MITIGATION_ACTION_STATUS_PATTERN,
    VENDOR_MITIGATION_ACTION_TYPE_PATTERN,
    VENDOR_MITIGATION_CASE_SEVERITY_PATTERN,
    VENDOR_MITIGATION_CASE_STATUS_PATTERN,
)

PORTAL_TOKEN_STATUS_PATTERN = "^(active|revoked|expired)$"


class VendorRemediationPortalTokenCreate(BaseModel):
    case_id: UUID
    vendor_contact_email: EmailStr
    vendor_contact_name: str | None = Field(default=None, max_length=255)
    scoped_action_ids: list[UUID] | None = None
    expires_in_days: int = Field(default=30, ge=1, le=90)


class VendorRemediationPortalTokenCreateResponse(BaseModel):
    token_id: UUID
    vendor_id: UUID
    case_id: UUID
    vendor_contact_email: EmailStr
    expires_at: datetime
    plaintext_token: str
    warning: str


class VendorRemediationPortalTokenRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID
    case_id: UUID
    vendor_contact_email: EmailStr
    vendor_contact_name: str | None = None
    masked_email: str
    scoped_action_ids: list[UUID] | None = None
    expires_at: datetime
    first_accessed_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int
    status: str = Field(pattern=PORTAL_TOKEN_STATUS_PATTERN)
    revoked_at: datetime | None = None
    revoked_by: UUID | None = None
    created_by: UUID
    created_at: datetime


class VendorRemediationPortalRevokeResponse(BaseModel):
    token_id: UUID
    status: str = Field(pattern=PORTAL_TOKEN_STATUS_PATTERN)


class VendorRemediationPortalVendorRead(BaseModel):
    id: UUID
    name: str
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None


class VendorRemediationPortalCaseRead(BaseModel):
    id: UUID
    title: str
    description: str
    severity: str = Field(pattern=VENDOR_MITIGATION_CASE_SEVERITY_PATTERN)
    status: str = Field(pattern=VENDOR_MITIGATION_CASE_STATUS_PATTERN)
    due_date: date


class VendorRemediationPortalMeResponse(BaseModel):
    vendor_contact_email: EmailStr
    vendor: VendorRemediationPortalVendorRead
    case: VendorRemediationPortalCaseRead
    expires_at: datetime
    access_count: int


class VendorRemediationPortalActionRead(BaseModel):
    id: UUID
    case_id: UUID
    title: str
    description: str
    action_type: str = Field(pattern=VENDOR_MITIGATION_ACTION_TYPE_PATTERN)
    due_date: date
    status: str = Field(pattern=VENDOR_MITIGATION_ACTION_STATUS_PATTERN)
    evidence_id: UUID | None = None
    evidence_submitted_at: datetime | None = None
    rejection_reason: str | None = None


class VendorRemediationPortalEvidenceSubmitRequest(BaseModel):
    remediation_notes: str = Field(min_length=1, max_length=5000)
    external_reference_url: str | None = Field(default=None, max_length=1024)
    file_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, max_length=128)


class VendorRemediationPortalEvidenceSubmitResponse(BaseModel):
    action: VendorRemediationPortalActionRead
    evidence_id: UUID
    message: str
