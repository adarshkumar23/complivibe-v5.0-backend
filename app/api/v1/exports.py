import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.export_job import ExportJob
from app.models.export_job_event import ExportJobEvent
from app.models.export_attestation import ExportAttestation
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.retention_policy import RetentionPolicy
from app.models.user import User
from app.repositories.attestation_repository import AttestationRepository
from app.repositories.export_repository import ExportRepository
from app.schemas.exports import (
    ExportAttestationCreate,
    ExportAttestationRead,
    ExportAttestationRevokeRequest,
    ExportJobCancelRequest,
    ExportJobCreate,
    ExportJobDetail,
    ExportJobEventRead,
    ExportJobListResponse,
    ExportJobRead,
    ExportJobRunResponse,
    ExportLegalHoldRequest,
    ExportManifestResponse,
    ExportPackageResponse,
    ExportRetentionApplyRequest,
    ExportSummaryResponse,
    ExportVerificationHistoryResponse,
    ExportVerifyResponse,
)
from app.services.attestation_service import AttestationService
from app.services.audit_service import AuditService
from app.services.export_service import ExportService
from app.services.rbac_service import RBACService
from app.services.retention_service import RetentionService

router = APIRouter(prefix="/exports", tags=["exports"])


def _job_read(service: ExportService, row: ExportJob) -> ExportJobRead:
    return ExportJobRead(**service.job_response_payload(row))


def _event_read(row: ExportJobEvent) -> ExportJobEventRead:
    return ExportJobEventRead(
        id=row.id,
        organization_id=row.organization_id,
        export_job_id=row.export_job_id,
        event_type=row.event_type,
        from_status=row.from_status,
        to_status=row.to_status,
        details_json=row.details_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _attestation_read(row: ExportAttestation) -> ExportAttestationRead:
    return ExportAttestationRead(
        id=row.id,
        organization_id=row.organization_id,
        export_job_id=row.export_job_id,
        attestation_type=row.attestation_type,
        statement=row.statement,
        status=row.status,
        attested_by_user_id=row.attested_by_user_id,
        attested_at=row.attested_at,
        revoked_by_user_id=row.revoked_by_user_id,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,
        export_checksum_sha256=row.export_checksum_sha256,
        export_integrity_signature=row.export_integrity_signature,
        attestation_checksum_sha256=row.attestation_checksum_sha256,
        attestation_signature=row.attestation_signature,
        signing_key_id=row.signing_key_id,
        signature_algorithm=row.signature_algorithm,
        valid_from=row.valid_from,
        not_after=row.not_after,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


@router.post("/jobs", response_model=ExportJobRead, status_code=status.HTTP_201_CREATED)
def create_export_job(
    payload: ExportJobCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:write")),
) -> ExportJobRead:
    service = ExportService(db)
    # A requested shorter validity window is carried on metadata_json so run_job can read
    # it when it signs (the signing key never leaves the service; validity_days is only an
    # input, and the enforced not_after is stored in its own signed column).
    metadata_json = dict(payload.metadata_json or {})
    if payload.validity_days is not None:
        metadata_json["validity_days"] = payload.validity_days
    row = service.create_job(
        organization_id=organization.id,
        export_type=payload.export_type,
        title=payload.title,
        description=payload.description,
        source_report_id=payload.source_report_id,
        framework_id=payload.framework_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        metadata_json=metadata_json or None,
        requested_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="export_job.created",
        entity_type="export_job",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"export_type": row.export_type, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _job_read(service, row)


@router.get("/jobs", response_model=ExportJobListResponse)
def list_export_jobs(
    export_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    framework_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:read")),
) -> ExportJobListResponse:
    service = ExportService(db)
    rows = ExportRepository(db).list_jobs(
        organization_id=organization.id,
        export_type=export_type,
        status=status_filter,
        framework_id=framework_id,
        limit=limit,
        offset=offset,
    )
    return ExportJobListResponse(jobs=[_job_read(service, row) for row in rows])


@router.get("/jobs/{export_job_id}", response_model=ExportJobDetail)
def get_export_job_detail(
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:read")),
) -> ExportJobDetail:
    service = ExportService(db)
    row = service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    events = ExportRepository(db).list_events(organization_id=organization.id, export_job_id=row.id)
    return ExportJobDetail(job=_job_read(service, row), events=[_event_read(item) for item in events])


@router.post("/jobs/{export_job_id}/run", response_model=ExportJobRunResponse)
def run_export_job(
    export_job_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:run")),
) -> ExportJobRunResponse:
    service = ExportService(db)
    row = service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    try:
        row = service.run_job(job=row, actor_user_id=current_user.id)
        AuditService(db).write_audit_log(
            action="export_job.completed",
            entity_type="export_job",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"status": row.status, "checksum_sha256": row.checksum_sha256},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        row = service.require_job(organization_id=organization.id, export_job_id=export_job_id)
        AuditService(db).write_audit_log(
            action="export_job.failed",
            entity_type="export_job",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"status": row.status, "error_message": str(exc)},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        raise
    db.refresh(row)
    return ExportJobRunResponse(job=_job_read(service, row))


@router.post("/jobs/{export_job_id}/cancel", response_model=ExportJobRead)
def cancel_export_job(
    export_job_id: uuid.UUID,
    payload: ExportJobCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:write")),
) -> ExportJobRead:
    service = ExportService(db)
    row = service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    row = service.cancel_job(job=row, actor_user_id=current_user.id, reason=payload.reason)
    AuditService(db).write_audit_log(
        action="export_job.cancelled",
        entity_type="export_job",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "reason": payload.reason},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _job_read(service, row)


@router.post("/jobs/{export_job_id}/archive", response_model=ExportJobRead)
def archive_export_job(
    export_job_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:write")),
) -> ExportJobRead:
    service = ExportService(db)
    row = service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    if row.status == "archived":
        return _job_read(service, row)
    row = service.archive_job(job=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="export_job.archived",
        entity_type="export_job",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _job_read(service, row)


@router.get("/jobs/{export_job_id}/package", response_model=ExportPackageResponse)
def get_export_package(
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:read")),
) -> ExportPackageResponse:
    row = ExportService(db).require_job(organization_id=organization.id, export_job_id=export_job_id)
    if row.status != "completed" or row.package_json is None or row.checksum_sha256 is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export package is not available")
    return ExportPackageResponse(
        export_job_id=row.id,
        checksum_sha256=row.checksum_sha256,
        signature_algorithm=row.signature_algorithm,
        signing_key_id=row.signing_key_id,
        integrity_signature=row.integrity_signature,
        valid_from=row.valid_from,
        not_after=row.not_after,
        package_json=row.package_json,
    )


@router.get("/jobs/{export_job_id}/manifest", response_model=ExportManifestResponse)
def get_export_manifest(
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:read")),
) -> ExportManifestResponse:
    row = ExportService(db).require_job(organization_id=organization.id, export_job_id=export_job_id)
    if row.status != "completed" or row.manifest_json is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export manifest is not available")
    return ExportManifestResponse(export_job_id=row.id, manifest_json=row.manifest_json)


@router.post("/jobs/{export_job_id}/verify", response_model=ExportVerifyResponse)
def verify_export_job(
    export_job_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:verify")),
) -> ExportVerifyResponse:
    service = ExportService(db)
    row = service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    result = service.verify_job(job=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="export_job.verified",
        entity_type="export_job",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "valid": result["valid"],
            "checksum_match": result["checksum_match"],
            "signature_match": result["signature_match"],
            "expired": result["expired"],
            "revoked": result["revoked"],
            "reason": result["reason"],
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return ExportVerifyResponse(
        export_job_id=row.id,
        valid=result["valid"],
        checksum_match=result["checksum_match"],
        signature_match=result["signature_match"],
        expired=result["expired"],
        revoked=result["revoked"],
        reason=result["reason"],
        not_after=result["not_after"],
        checked_at=result["checked_at"],
    )


@router.get("/summary", response_model=ExportSummaryResponse)
def export_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exports:read")),
) -> ExportSummaryResponse:
    return ExportSummaryResponse(**ExportService(db).summary(organization_id=organization.id))


@router.post("/jobs/{export_job_id}/retention/apply", response_model=ExportJobRead)
def apply_retention_policy_to_export(
    export_job_id: uuid.UUID,
    payload: ExportRetentionApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("retention:write")),
) -> ExportJobRead:
    export_service = ExportService(db)
    retention_service = RetentionService(db)
    row = export_service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    policy: RetentionPolicy | None = None
    if payload.policy_id is not None:
        policy = retention_service.require_policy(organization.id, payload.policy_id)
    row = retention_service.apply_policy_to_export(
        job=row,
        actor_user_id=current_user.id,
        policy=policy,
        lock_days=payload.lock_days,
        retention_days=payload.retention_days,
    )
    export_service.add_event(
        job=row,
        event_type="export.retention_applied",
        from_status=row.status,
        to_status=row.status,
        details_json={
            "policy_id": str(policy.id) if policy else None,
            "lock_days": payload.lock_days if payload.lock_days is not None else (policy.lock_days if policy else 0),
            "retention_days": payload.retention_days if payload.retention_days is not None else (policy.retention_days if policy else 0),
            "locked_until": row.locked_until.isoformat() if row.locked_until else None,
            "retention_until": row.retention_until.isoformat() if row.retention_until else None,
            "legal_hold": row.legal_hold,
        },
        created_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="export_job.retention_applied",
        entity_type="export_job",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "locked_until": row.locked_until.isoformat() if row.locked_until else None,
            "retention_until": row.retention_until.isoformat() if row.retention_until else None,
            "legal_hold": row.legal_hold,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _job_read(export_service, row)


@router.post("/jobs/{export_job_id}/legal-hold", response_model=ExportJobRead)
def set_export_legal_hold(
    export_job_id: uuid.UUID,
    payload: ExportLegalHoldRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("retention:write")),
) -> ExportJobRead:
    export_service = ExportService(db)
    retention_service = RetentionService(db)
    row = export_service.require_job(organization_id=organization.id, export_job_id=export_job_id)
    row = retention_service.set_legal_hold(
        job=row,
        actor_user_id=current_user.id,
        enabled=payload.enabled,
        reason=payload.reason,
    )
    export_service.add_event(
        job=row,
        event_type="export.legal_hold_updated",
        from_status=row.status,
        to_status=row.status,
        details_json={"enabled": row.legal_hold, "reason": payload.reason},
        created_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="export_job.legal_hold_updated",
        entity_type="export_job",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "legal_hold": row.legal_hold,
            "legal_hold_reason": row.legal_hold_reason,
            "legal_hold_set_at": row.legal_hold_set_at.isoformat() if row.legal_hold_set_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _job_read(export_service, row)


@router.post("/jobs/{export_job_id}/attestations", response_model=ExportAttestationRead, status_code=status.HTTP_201_CREATED)
def create_export_attestation(
    export_job_id: uuid.UUID,
    payload: ExportAttestationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("attestations:write")),
) -> ExportAttestationRead:
    export_service = ExportService(db)
    attestation_service = AttestationService(db)
    row = export_service.require_job(organization_id=organization.id, export_job_id=export_job_id)

    verification = export_service.verify_job(job=row, actor_user_id=current_user.id)
    if not verification["valid"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export verification failed; cannot attest")

    attestation = attestation_service.create_attestation(
        job=row,
        actor_user_id=current_user.id,
        attestation_type=payload.attestation_type,
        statement=payload.statement,
        metadata_json=payload.metadata_json,
    )
    export_service.add_event(
        job=row,
        event_type="export.attested",
        from_status=row.status,
        to_status=row.status,
        details_json={"attestation_id": str(attestation.id), "attestation_type": attestation.attestation_type},
        created_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="export_attestation.created",
        entity_type="export_attestation",
        entity_id=attestation.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"export_job_id": str(row.id), "attestation_type": attestation.attestation_type, "status": attestation.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(attestation)
    return _attestation_read(attestation)


@router.get("/jobs/{export_job_id}/attestations", response_model=list[ExportAttestationRead])
def list_export_attestations(
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("attestations:read")),
) -> list[ExportAttestationRead]:
    row = ExportService(db).require_job(organization_id=organization.id, export_job_id=export_job_id)
    items = AttestationRepository(db).list_for_export(organization.id, row.id)
    return [_attestation_read(item) for item in items]


@router.get("/jobs/{export_job_id}/verification-history", response_model=ExportVerificationHistoryResponse)
def export_verification_history(
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> ExportVerificationHistoryResponse:
    if not (
        RBACService.user_has_permission(db, current_user.id, organization.id, "exports:verify")
        or RBACService.user_has_permission(db, current_user.id, organization.id, "attestations:read")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: exports:verify or attestations:read")

    row = ExportService(db).require_job(organization_id=organization.id, export_job_id=export_job_id)
    events = ExportService(db).verification_history(organization_id=organization.id, export_job_id=row.id)
    return ExportVerificationHistoryResponse(
        export_job_id=row.id,
        verifications=[_event_read(item) for item in events],
    )
