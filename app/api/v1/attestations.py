import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.repositories.attestation_repository import AttestationRepository
from app.services.attestation_service import AttestationService
from app.services.audit_service import AuditService
from app.services.export_service import ExportService
from app.schemas.exports import ExportAttestationRead, ExportAttestationRevokeRequest

router = APIRouter(prefix="/attestations", tags=["attestations"])


def _attestation_read(row) -> ExportAttestationRead:
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


@router.get("/{attestation_id}", response_model=ExportAttestationRead)
def get_attestation_detail(
    attestation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:read")),
) -> ExportAttestationRead:
    row = AttestationService(db).require_attestation(organization_id=organization.id, attestation_id=attestation_id)
    return _attestation_read(row)


@router.post("/{attestation_id}/revoke", response_model=ExportAttestationRead)
def revoke_attestation(
    attestation_id: uuid.UUID,
    payload: ExportAttestationRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:revoke")),
) -> ExportAttestationRead:
    service = AttestationService(db)
    row = service.require_attestation(organization_id=organization.id, attestation_id=attestation_id)
    job = ExportService(db).require_job(organization_id=organization.id, export_job_id=row.export_job_id)
    row = service.revoke_attestation(
        row=row,
        job=job,
        actor_user_id=current_user.id,
        revocation_reason=payload.revocation_reason,
    )
    ExportService(db).add_event(
        job=job,
        event_type="export.attestation_revoked",
        from_status=job.status,
        to_status=job.status,
        details_json={"attestation_id": str(row.id), "reason": row.revocation_reason},
        created_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="export_attestation.revoked",
        entity_type="export_attestation",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": "active"},
        after_json={"status": row.status, "revocation_reason": row.revocation_reason},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _attestation_read(row)
