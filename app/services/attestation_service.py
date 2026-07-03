import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.export_attestation import ExportAttestation
from app.models.export_job import ExportJob
from app.repositories.attestation_repository import AttestationRepository
from app.services.export_service import INTEGRITY_ALGORITHM, SIGNING_KEY_ID
from app.core.validation import validate_choice

ALLOWED_ATTESTATION_TYPES = {
    "internal_review",
    "compliance_owner_review",
    "auditor_review",
    "executive_review",
}


class AttestationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AttestationRepository(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def validate_attestation_type(attestation_type: str) -> None:
        attestation_type = validate_choice(attestation_type, ALLOWED_ATTESTATION_TYPES, "attestation_type", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def checksum(self, payload: dict[str, Any]) -> str:
        canonical = self.canonical_json(payload).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def signature(self, checksum_sha256: str) -> str:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        return hmac.new(secret, checksum_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_attestation(
        self,
        *,
        job: ExportJob,
        actor_user_id: uuid.UUID,
        attestation_type: str,
        statement: str,
        metadata_json: dict | None,
    ) -> ExportAttestation:
        self.validate_attestation_type(attestation_type)
        if job.status != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attestation requires completed export")
        if job.checksum_sha256 is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export checksum missing")

        attested_at = self.now()
        payload = {
            "organization_id": str(job.organization_id),
            "export_job_id": str(job.id),
            "attestation_type": attestation_type,
            "statement": statement,
            "attested_by_user_id": str(actor_user_id),
            "attested_at": attested_at.isoformat(),
            "export_checksum_sha256": job.checksum_sha256,
            "export_integrity_signature": job.integrity_signature,
        }
        attestation_checksum = self.checksum(payload)
        attestation_signature = self.signature(attestation_checksum)

        row = ExportAttestation(
            organization_id=job.organization_id,
            export_job_id=job.id,
            attestation_type=attestation_type,
            statement=statement,
            status="active",
            attested_by_user_id=actor_user_id,
            attested_at=attested_at,
            export_checksum_sha256=job.checksum_sha256,
            export_integrity_signature=job.integrity_signature,
            attestation_checksum_sha256=attestation_checksum,
            attestation_signature=attestation_signature,
            signing_key_id=SIGNING_KEY_ID,
            signature_algorithm=INTEGRITY_ALGORITHM,
            metadata_json=metadata_json,
            created_at=attested_at,
        )
        self.db.add(row)
        self.db.flush()

        job.attestation_status = "attested"
        job.latest_attestation_id = row.id
        self.db.flush()
        return row

    def require_attestation(self, *, organization_id: uuid.UUID, attestation_id: uuid.UUID) -> ExportAttestation:
        row = self.repo.get_attestation(attestation_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation not found")
        return row

    def revoke_attestation(
        self,
        *,
        row: ExportAttestation,
        job: ExportJob,
        actor_user_id: uuid.UUID,
        revocation_reason: str,
    ) -> ExportAttestation:
        if not revocation_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="revocation_reason is required")
        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attestation is already revoked")

        row.status = "revoked"
        row.revoked_by_user_id = actor_user_id
        row.revoked_at = self.now()
        row.revocation_reason = revocation_reason
        self.db.flush()

        latest_active = self.repo.latest_active_for_export(row.organization_id, row.export_job_id)
        if latest_active is None:
            job.attestation_status = "revoked"
            job.latest_attestation_id = None
        else:
            job.attestation_status = "attested"
            job.latest_attestation_id = latest_active.id
        self.db.flush()
        return row
