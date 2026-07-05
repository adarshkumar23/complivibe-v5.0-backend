import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content_provenance_record import ContentProvenanceRecord
from app.services.audit_service import AuditService

# Manifest structural validation is implemented directly against the public
# C2PA specification shape (claim_generator, spec/claim version, assertions,
# signature block, optional ingredients) rather than by pulling in a
# third-party binding. The only widely available Python package for this
# space is built to embed/extract C2PA manifests inside real media files via
# a compiled native binary -- it is not designed to validate a standalone
# manifest payload, and dragging in a ~15MB native dependency for what is
# fundamentally a JSON-shape/plausibility check would be a poor trade.
# Everything below is a STRUCTURAL check only -- it does not perform
# cryptographic signature verification.
SUPPORTED_SPEC_VERSIONS = {
    "c2pa-1.0",
    "c2pa-1.1",
    "c2pa-1.2",
    "c2pa-1.3",
    "1.0",
    "1.1",
    "1.2",
    "1.3",
}


class ContentProvenanceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def _validate_c2pa_structure(
        self, manifest: dict
    ) -> tuple[str, str | None, str | None, str | None, int | None]:
        """Run structural validation of a submitted manifest payload.

        Returns (status, reason, spec_version_detected, claim_generator, assertion_count).
        ``reason`` is None when status == "valid".
        """
        if not isinstance(manifest, dict):
            return "invalid", "malformed_claim", None, None, None

        claim_generator = manifest.get("claim_generator")
        assertions = manifest.get("assertions")
        spec_version = manifest.get("spec_version") or manifest.get("claim_version")

        malformed = (
            not isinstance(claim_generator, str)
            or not claim_generator.strip()
            or not isinstance(assertions, list)
            or len(assertions) == 0
            or not all(
                isinstance(item, dict) and item.get("label") and "data" in item for item in assertions
            )
        )
        if malformed:
            return "invalid", "malformed_claim", None, claim_generator if isinstance(claim_generator, str) else None, (
                len(assertions) if isinstance(assertions, list) else None
            )

        if spec_version is not None and (not isinstance(spec_version, str) or not spec_version.strip()):
            spec_version = None

        if spec_version is not None and spec_version not in SUPPORTED_SPEC_VERSIONS:
            return "invalid", "unsupported_version", spec_version, claim_generator, len(assertions)

        signature_block = manifest.get("signature_info")
        if signature_block is None:
            signature_block = manifest.get("signature")
        if signature_block is None:
            return "invalid", "missing_signature", spec_version, claim_generator, len(assertions)

        if not isinstance(signature_block, dict):
            return "invalid", "tampered_signature", spec_version, claim_generator, len(assertions)

        algorithm = signature_block.get("algorithm") or signature_block.get("alg")
        signature_value = signature_block.get("signature") or signature_block.get("value")
        if (
            not isinstance(algorithm, str)
            or not algorithm.strip()
            or not isinstance(signature_value, str)
            or not signature_value.strip()
        ):
            return "invalid", "tampered_signature", spec_version, claim_generator, len(assertions)

        return "valid", None, spec_version, claim_generator, len(assertions)

    def verify_manifest(
        self,
        org_id: uuid.UUID,
        content_identifier: str,
        manifest: dict,
        actor_id: uuid.UUID | None,
    ) -> ContentProvenanceRecord:
        (
            status_value,
            reason,
            spec_version_detected,
            claim_generator,
            assertion_count,
        ) = self._validate_c2pa_structure(manifest)

        record = ContentProvenanceRecord(
            organization_id=org_id,
            content_identifier=content_identifier,
            raw_manifest=manifest,
            verification_status=status_value,
            invalid_reason=reason,
            spec_version_detected=spec_version_detected,
            claim_generator=claim_generator,
            assertion_count=assertion_count,
            verified_at=self._utcnow(),
            created_by=actor_id,
        )
        self.db.add(record)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="content_provenance.manifest_verified",
            entity_type="content_provenance_record",
            entity_id=record.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "content_identifier": content_identifier,
                "verification_status": status_value,
            },
            metadata_json={
                "verification_status": status_value,
                "invalid_reason": reason,
                "spec_version_detected": spec_version_detected,
            },
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_record(self, org_id: uuid.UUID, record_id: uuid.UUID) -> ContentProvenanceRecord:
        row = self.db.execute(
            select(ContentProvenanceRecord).where(
                ContentProvenanceRecord.organization_id == org_id,
                ContentProvenanceRecord.id == record_id,
                ContentProvenanceRecord.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content provenance record not found")
        return row
