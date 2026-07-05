from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class OrganizationRead(UUIDTimestampSchema):
    name: str
    slug: str | None = None
    is_active: bool
    is_significant_data_fiduciary: bool
    sdf_category: str | None = None
    dpdp_registration_number: str | None = None
    consent_manager_registered: bool
    sanctions_match_threshold: float = 0.85


class OrganizationSummary(BaseModel):
    id: UUID
    name: str
    slug: str | None = None


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_active: bool | None = None
    is_significant_data_fiduciary: bool | None = None
    sdf_category: str | None = Field(default=None, max_length=100)
    dpdp_registration_number: str | None = Field(default=None, max_length=100)
    consent_manager_registered: bool | None = None
    sanctions_match_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class OrganizationUpdateResponse(BaseModel):
    organization: OrganizationRead
    audit: dict[str, Any]


class OrganizationGovernanceSettingsRead(BaseModel):
    batch_cancellation_requires_approval: bool = False
    batch_cancellation_policy_reason: str | None = None
    updated_by_user_id: UUID | None = None
    updated_at: datetime | None = None


class OrganizationGovernanceSettingsUpdateRequest(BaseModel):
    batch_cancellation_requires_approval: bool | None = None
    batch_cancellation_policy_reason: str | None = Field(default=None, min_length=3, max_length=2000)


class OrganizationGovernanceApplyToOpenBatchRunsRequest(BaseModel):
    dry_run: bool = True
    reason: str = Field(min_length=3, max_length=2000)


class OrganizationGovernanceApplyToOpenBatchRunsResponse(BaseModel):
    dry_run: bool
    target_value: bool
    eligible_count: int
    updated_count: int
    skipped_count: int
    affected_run_ids: list[UUID]
    skipped_reasons: dict[str, int]
    caveat: str


class OrganizationGovernanceSettingHistoryRead(BaseModel):
    id: UUID
    organization_id: UUID
    version: int
    event_type: str
    setting_key: str
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    reason: str
    affected_entity_type: str | None = None
    affected_entity_ids_json: list[str] | None = None
    skipped_summary_json: dict[str, int] | None = None
    changed_by_user_id: UUID | None = None
    audit_log_id: UUID | None = None
    created_at: datetime


class OrganizationGovernanceTimelineEntry(BaseModel):
    timestamp: datetime
    event_type: str
    actor_user_id: UUID | None = None
    summary: str
    source: str
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None


class OrganizationGovernanceTimelineResponse(BaseModel):
    entries: list[OrganizationGovernanceTimelineEntry]
    caveat: str


class OrganizationGovernanceSettingsDiffResponse(BaseModel):
    from_version: int
    to_version: int
    changed_keys: list[str]
    before_json: dict[str, Any]
    after_json: dict[str, Any]
    entries_compared: int
    caveat: str


class OrganizationGovernanceEvidenceBundleResponse(BaseModel):
    current_settings: OrganizationGovernanceSettingsRead
    history_entries: list[OrganizationGovernanceSettingHistoryRead]
    latest_rollout_summary: dict[str, Any] | None = None
    relevant_audit_action_names: list[str]
    caveat: str


class OrganizationGovernanceEvidenceManifestGenerateRequest(BaseModel):
    include_history: bool = True
    include_timeline: bool = True
    include_audit_actions: bool = True
    from_version: int | None = Field(default=None, ge=1)
    to_version: int | None = Field(default=None, ge=1)


class OrganizationGovernanceEvidenceManifestRead(BaseModel):
    id: UUID
    organization_id: UUID
    manifest_type: str
    status: str
    content_sha256: str
    signature_algorithm: str
    internal_signature: str
    key_id: str | None = None
    generated_by_user_id: UUID | None = None
    generated_at: datetime
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None
    revocation_reason: str | None = None
    created_at: datetime


class OrganizationGovernanceEvidenceManifestGenerateResponse(BaseModel):
    manifest_id: UUID
    manifest_type: str
    status: str
    key_id: str | None = None
    content_sha256: str
    signature_algorithm: str
    internal_signature: str
    generated_by_user_id: UUID | None = None
    generated_at: datetime
    caveat: str


class OrganizationGovernanceEvidenceManifestDetailResponse(BaseModel):
    manifest: OrganizationGovernanceEvidenceManifestRead
    manifest_json: dict[str, Any]
    caveat: str


class OrganizationGovernanceEvidenceManifestListResponse(BaseModel):
    manifests: list[OrganizationGovernanceEvidenceManifestRead]
    caveat: str


class OrganizationGovernanceEvidenceManifestVerifyResponse(BaseModel):
    valid_hash: bool
    valid_signature: bool
    trusted: bool
    status: str
    key_id: str | None = None
    key_status: str | None = None
    legacy_verification: bool = False
    content_sha256: str
    recomputed_sha256: str
    verification_event_id: UUID | None = None
    caveat: str


class OrganizationGovernanceEvidenceManifestRevokeRequest(BaseModel):
    revocation_reason: str = Field(min_length=3, max_length=2000)


class OrganizationInternalSigningKeyRead(BaseModel):
    id: UUID
    organization_id: UUID
    key_id: str
    algorithm: str
    status: str
    purpose: str
    created_by_user_id: UUID | None = None
    activated_at: datetime | None = None
    deprecated_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationInternalSigningKeyListResponse(BaseModel):
    keys: list[OrganizationInternalSigningKeyRead]
    caveat: str


class OrganizationInternalSigningKeyActionResponse(BaseModel):
    key: OrganizationInternalSigningKeyRead
    caveat: str


class OrganizationInternalSigningKeyReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class OrganizationInternalSigningKeyRevokeRequest(BaseModel):
    revocation_reason: str = Field(min_length=3, max_length=2000)


class OrganizationInternalSigningKeySummaryResponse(BaseModel):
    active_keys: int
    deprecated_keys: int
    revoked_keys: int
    manifests_by_key_id: dict[str, int]
    legacy_manifests_without_key_id: int
    caveat: str


class OrganizationGovernanceManifestVerificationEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    manifest_id: UUID
    verified_by_user_id: UUID | None = None
    verified_at: datetime
    valid_hash: bool
    valid_signature: bool
    trusted: bool
    key_id: str | None = None
    key_status: str | None = None
    legacy_verification: bool = False
    content_sha256: str
    recomputed_sha256: str
    signature_algorithm: str
    verification_result_json: dict[str, Any]
    caveat: str
    created_at: datetime


class OrganizationGovernanceManifestVerificationEventListResponse(BaseModel):
    events: list[OrganizationGovernanceManifestVerificationEventRead]
    caveat: str


class OrganizationGovernanceManifestChainEntry(BaseModel):
    timestamp: datetime
    event_type: str
    source: str
    actor_user_id: UUID | None = None
    summary: str
    details_json: dict[str, Any] | None = None


class OrganizationGovernanceManifestChainResponse(BaseModel):
    entries: list[OrganizationGovernanceManifestChainEntry]
    caveat: str


class OrganizationGovernanceManifestVerificationSummaryResponse(BaseModel):
    total_verifications: int
    trusted_verifications: int
    untrusted_verifications: int
    failed_hash_verifications: int
    failed_signature_verifications: int
    legacy_verifications: int
    revoked_key_verifications: int
    latest_verification_at: datetime | None = None
    caveat: str


class OrganizationGovernanceManifestVerificationEventExportRequest(BaseModel):
    manifest_id: UUID | None = None
    trusted: bool | None = None
    key_id: str | None = Field(default=None, min_length=1, max_length=128)
    legacy_verification: bool | None = None
    from_verified_at: datetime | None = None
    to_verified_at: datetime | None = None
    direction: str = Field(default="asc", pattern="^(asc|desc)$")
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = None
    include_manifest_metadata: bool = True
    include_chain_context: bool = False
    include_internal_signature: bool = True


class OrganizationGovernanceManifestVerificationEventExportPage(BaseModel):
    limit: int
    direction: str
    next_cursor: str | None = None
    has_more: bool
    item_count: int


class OrganizationGovernanceManifestVerificationEventExportIntegrity(BaseModel):
    canonical_page_sha256: str
    record_count: int
    filters_hash: str
    cursor_version: int
    internal_signature: str | None = None
    signature_algorithm: str | None = None
    key_id: str | None = None
    key_status: str | None = None
    signature_scope: str | None = None
    signed_payload_sha256: str | None = None


class OrganizationGovernanceManifestVerificationEventExportResponse(BaseModel):
    export_type: str
    generated_at: datetime
    organization_id: UUID
    filters: dict[str, Any]
    page: OrganizationGovernanceManifestVerificationEventExportPage
    events: list[OrganizationGovernanceManifestVerificationEventRead]
    manifest_metadata: dict[str, Any] | None = None
    chain_context: dict[str, Any] | None = None
    export_integrity: OrganizationGovernanceManifestVerificationEventExportIntegrity
    caveat: str


class OrganizationGovernanceManifestVerificationEventExportVerifyPageRequest(BaseModel):
    exported_page_json: dict[str, Any]


class OrganizationGovernanceManifestVerificationEventExportVerifyPageResponse(BaseModel):
    valid_signature: bool
    valid_signed_payload_hash: bool
    valid_canonical_page_hash: bool
    key_id: str | None = None
    key_status: str | None = None
    trusted: bool
    signature_scope: str
    signature_algorithm: str
    caveat: str
