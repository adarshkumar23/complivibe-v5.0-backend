from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ExportJobCreate(BaseModel):
    export_type: str
    title: str | None = None
    description: str | None = None
    source_report_id: UUID | None = None
    framework_id: UUID | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    metadata_json: dict | None = None
    # Optional shorter signature validity window (days). Omit for the 1-year default;
    # a value above 365 is clamped down -- callers may only request a SHORTER window.
    validity_days: int | None = Field(default=None, ge=1)


class ExportJobRead(BaseModel):
    id: UUID
    organization_id: UUID
    export_type: str
    title: str
    description: str | None = None
    status: str
    requested_by_user_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    archived_at: datetime | None = None
    error_message: str | None = None
    source_report_id: UUID | None = None
    framework_id: UUID | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    checksum_sha256: str | None = None
    integrity_signature: str | None = None
    signing_key_id: str | None = None
    signature_algorithm: str | None = None
    # The signed validity window (0318). Both are covered by integrity_signature, so a
    # reader needs them to know whether the signature it is looking at is still good --
    # without having to call the verify endpoint to find out.
    valid_from: datetime | None = None
    not_after: datetime | None = None
    locked_until: datetime | None = None
    retention_until: datetime | None = None
    legal_hold: bool
    legal_hold_reason: str | None = None
    legal_hold_set_by_user_id: UUID | None = None
    legal_hold_set_at: datetime | None = None
    attestation_status: str
    latest_attestation_id: UUID | None = None
    package_version: str
    immutable_after_completion: bool
    metadata_json: dict | None = None
    age_days: int
    is_terminal: bool
    is_integrity_bound: bool
    context_flags: list[str]
    created_at: datetime
    updated_at: datetime


class ExportJobEventRead(BaseModel):
    id: UUID
    organization_id: UUID
    export_job_id: UUID
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    details_json: dict | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime


class ExportJobDetail(BaseModel):
    job: ExportJobRead
    events: list[ExportJobEventRead]


class ExportJobListResponse(BaseModel):
    jobs: list[ExportJobRead]


class ExportJobRunResponse(BaseModel):
    job: ExportJobRead


class ExportJobCancelRequest(BaseModel):
    reason: str | None = None


class ExportRetentionApplyRequest(BaseModel):
    policy_id: UUID | None = None
    lock_days: int | None = Field(default=None, ge=0)
    retention_days: int | None = Field(default=None, ge=0)


class ExportLegalHoldRequest(BaseModel):
    enabled: bool
    reason: str | None = None


class ExportPackageResponse(BaseModel):
    export_job_id: UUID
    checksum_sha256: str
    signature_algorithm: str | None = None
    signing_key_id: str | None = None
    integrity_signature: str | None = None
    valid_from: datetime | None = None
    not_after: datetime | None = None
    package_json: dict


class ExportManifestResponse(BaseModel):
    export_job_id: UUID
    manifest_json: dict


class ExportVerifyResponse(BaseModel):
    export_job_id: UUID
    valid: bool
    checksum_match: bool
    signature_match: bool | None = None
    expired: bool = False
    revoked: bool = False
    reason: str | None = None
    not_after: datetime | None = None
    checked_at: datetime


class ExportSummaryResponse(BaseModel):
    total_exports: int
    queued_exports: int
    processing_exports: int
    completed_exports: int
    failed_exports: int
    archived_exports: int
    exports_last_30d: int
    stale_queued_exports_24h: int
    verification_coverage_pct: float
    context_flags: list[str]
    latest_completed_at: datetime | None = None
    latest_verified_at: datetime | None = None


class ExportAttestationCreate(BaseModel):
    attestation_type: str
    statement: str
    metadata_json: dict | None = None


class ExportAttestationRead(BaseModel):
    id: UUID
    organization_id: UUID
    export_job_id: UUID
    attestation_type: str
    statement: str
    status: str
    attested_by_user_id: UUID
    attested_at: datetime
    revoked_by_user_id: UUID | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    export_checksum_sha256: str
    export_integrity_signature: str | None = None
    attestation_checksum_sha256: str
    attestation_signature: str | None = None
    signing_key_id: str | None = None
    signature_algorithm: str | None = None
    valid_from: datetime | None = None
    not_after: datetime | None = None
    metadata_json: dict | None = None
    created_at: datetime


class ExportAttestationRevokeRequest(BaseModel):
    revocation_reason: str


class RetentionPolicyCreate(BaseModel):
    name: str
    description: str | None = None
    entity_type: str
    retention_days: int = Field(ge=0)
    lock_days: int = Field(ge=0)
    legal_hold_default: bool = False
    status: str = "active"


class RetentionPolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    retention_days: int | None = Field(default=None, ge=0)
    lock_days: int | None = Field(default=None, ge=0)
    legal_hold_default: bool | None = None
    status: str | None = None


class RetentionPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    entity_type: str
    retention_days: int
    lock_days: int
    legal_hold_default: bool
    status: str
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class RetentionEvaluateRequest(BaseModel):
    entity_type: str | None = None
    dry_run: bool = True


class RetentionEvaluateResponse(BaseModel):
    dry_run: bool
    retained: list[dict]
    locked: list[dict]
    under_legal_hold: list[dict]
    retention_elapsed: list[dict]
    eligible_for_archive: list[dict]


class GovernanceRetentionSummary(BaseModel):
    active_policies: int
    locked_exports: int
    exports_under_legal_hold: int
    retention_elapsed_exports: int
    active_attestations: int
    revoked_attestations: int
    verifications_last_30d: int


class ExportVerificationHistoryResponse(BaseModel):
    export_job_id: UUID
    verifications: list[ExportJobEventRead]


class ExportJobListQuery(BaseModel):
    export_type: str | None = None
    status: str | None = None
    framework_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
