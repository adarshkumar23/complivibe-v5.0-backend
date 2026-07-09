from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

TRUST_CENTER_UPTIME_STATUS_PATTERN = "^(operational|degraded|partial_outage|major_outage|maintenance)$"
TRUST_CENTER_ACCESS_REQUEST_STATUS_PATTERN = "^(pending|approved|rejected|expired)$"


class TrustCenterConfigurationUpsert(BaseModel):
    is_enabled: bool = False
    display_name: str | None = Field(default=None, max_length=255)
    tagline: str | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    show_certifications: bool = True
    show_framework_coverage: bool = True
    show_published_policies: bool = True
    show_uptime_status: bool = False
    uptime_status: str | None = Field(default=None, pattern=TRUST_CENTER_UPTIME_STATUS_PATTERN)
    contact_email: str | None = Field(default=None, max_length=255)
    request_access_enabled: bool = True
    custom_message: str | None = None


class TrustCenterConfigurationRead(BaseModel):
    id: UUID
    organization_id: UUID
    is_enabled: bool
    display_name: str | None = None
    tagline: str | None = None
    logo_url: str | None = None
    show_certifications: bool
    show_framework_coverage: bool
    show_published_policies: bool
    show_uptime_status: bool
    uptime_status: str | None = Field(default=None, pattern=TRUST_CENTER_UPTIME_STATUS_PATTERN)
    uptime_updated_at: datetime | None = None
    contact_email: str | None = None
    request_access_enabled: bool
    custom_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TrustCenterSetSlugRequest(BaseModel):
    slug: str = Field(pattern="^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
    # Required (and must be true) to change a slug that's already set to something
    # else -- the slug is the org's public trust-center URL, so changing it silently
    # breaks any link/bookmark/integration already pointing at the old one. Left
    # False/omitted, set_org_slug() rejects the change with a warning instead of
    # applying it. Not required when setting a slug for the first time (previous
    # value None).
    confirm: bool = False


class TrustCenterSetSlugResponse(BaseModel):
    organization_id: UUID
    slug: str


class TrustCenterPublishPolicyRequest(BaseModel):
    policy_id: UUID
    summary: str | None = None


class TrustCenterPublishedPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    policy_id: UUID
    policy_title: str
    summary: str | None = None
    published_at: datetime
    published_by: UUID
    is_active: bool
    policy_archived: bool = False
    policy_updated_since_published: bool = False
    policy_last_updated_at: datetime | None = None


class TrustCenterAccessRequestCreate(BaseModel):
    requester_name: str = Field(min_length=1, max_length=255)
    requester_email: str = Field(min_length=1, max_length=255)
    requester_company: str | None = Field(default=None, max_length=255)
    request_reason: str | None = None


class TrustCenterAccessRequestReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    notes: str | None = None


class TrustCenterAccessRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    requester_name: str
    requester_email: str
    requester_company: str | None = None
    request_reason: str | None = None
    status: str = Field(pattern=TRUST_CENTER_ACCESS_REQUEST_STATUS_PATTERN)
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    access_token_hash: str | None = None
    access_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TrustCenterAccessRequestSubmitResponse(BaseModel):
    request_id: UUID
    message: str
    duplicate: bool = False


class TrustCenterCertificationPublicRead(BaseModel):
    name: str
    issued_by: str | None = None
    valid_until: date | None = None


class TrustCenterFrameworkCoverageRead(BaseModel):
    framework_name: str
    coverage_pct: int


class TrustCenterPolicyPublicRead(BaseModel):
    title: str
    summary: str | None = None


class TrustCenterPublicUptimeRead(BaseModel):
    status: str = Field(pattern=TRUST_CENTER_UPTIME_STATUS_PATTERN)
    updated_at: datetime | None = None


class TrustCenterPublicRead(BaseModel):
    organization_slug: str
    display_name: str
    tagline: str | None = None
    logo_url: str | None = None
    contact_email: str | None = None
    custom_message: str | None = None
    certifications: list[TrustCenterCertificationPublicRead]
    framework_coverage: list[TrustCenterFrameworkCoverageRead]
    policies: list[TrustCenterPolicyPublicRead]
    competitor_pricing: list[dict] = Field(default_factory=list)
    competitor_pricing_last_updated: datetime | None = None
    uptime: TrustCenterPublicUptimeRead | None = None
    data_generated_at: datetime
    expired_certifications_excluded: int = 0


class TrustCenterUptimeUpdateRequest(BaseModel):
    status: str = Field(pattern=TRUST_CENTER_UPTIME_STATUS_PATTERN)
