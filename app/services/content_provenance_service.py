import uuid
import base64
import binascii
import copy
import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
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
#
# Structural checks alone (claim_generator, assertions, presence of a
# signature block) cannot detect tampering -- per the C2PA spec, the only
# way to detect tampering is a "hard binding": a cryptographic hash tied to
# the exact bytes of the asset, which is invalidated the instant a single
# byte of the asset changes (spec.c2pa.org, C2PA Technical Specification,
# "Hard Bindings"). Full COSE_Sign1 / X.509 trust-chain signature
# verification is out of scope here (no PKI/trust-list infrastructure exists
# elsewhere in this codebase), but hard-binding hash comparison against the
# real asset is real, computable cryptographic verification and is
# implemented below: when the caller supplies the actual asset's SHA-256
# digest (content_sha256), it is compared against the manifest's
# c2pa.hash.* hard-binding assertion. A mismatch is a genuine, real
# detection of tampering -- not a shape check.
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

    @staticmethod
    def _hard_binding_hash(assertions: list) -> str | None:
        """Extract the declared hash value from a c2pa.hash.* hard-binding assertion, if present."""
        for item in assertions:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            if not isinstance(label, str) or not label.startswith("c2pa.hash."):
                continue
            data = item.get("data")
            if isinstance(data, dict):
                hash_value = data.get("hash")
                if isinstance(hash_value, str) and hash_value.strip():
                    return hash_value.strip()
        return None

    @staticmethod
    def _decode_signature_bytes(value: str) -> bytes:
        stripped = value.strip()
        try:
            return base64.b64decode(stripped, validate=True)
        except (binascii.Error, ValueError):
            try:
                return bytes.fromhex(stripped)
            except ValueError as exc:
                raise ValueError("signature value is not base64 or hex") from exc

    @staticmethod
    def _canonical_claim_bytes(manifest: dict) -> bytes:
        claim = copy.deepcopy(manifest)
        claim.pop("signature_info", None)
        claim.pop("signature", None)
        return json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def _verify_signature_block(cls, manifest: dict, signature_block: dict) -> bool:
        """Verify an Ed25519 signature over the canonical claim JSON.

        The signed payload is the submitted manifest with its signature block removed.
        That makes claim tampering fail verification even when the signature remains
        syntactically well-formed.
        """
        algorithm = signature_block.get("algorithm") or signature_block.get("alg")
        signature_value = signature_block.get("signature") or signature_block.get("value")
        public_key_value = signature_block.get("public_key") or signature_block.get("publicKey")
        if (
            not isinstance(algorithm, str)
            or algorithm.strip().lower() not in {"ed25519", "eddsa-ed25519"}
            or not isinstance(signature_value, str)
            or not signature_value.strip()
            or not isinstance(public_key_value, str)
            or not public_key_value.strip()
        ):
            return False

        try:
            public_key_bytes = cls._decode_signature_bytes(public_key_value)
            signature_bytes = cls._decode_signature_bytes(signature_value)
            Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
                signature_bytes,
                cls._canonical_claim_bytes(manifest),
            )
        except (ValueError, InvalidSignature):
            return False
        return True

    def _validate_c2pa_structure(
        self, manifest: dict, content_sha256: str | None = None
    ) -> tuple[str, str | None, str | None, str | None, int | None]:
        """Run structural validation of a submitted manifest payload.

        Returns (status, reason, spec_version_detected, claim_generator, assertion_count).
        ``reason`` is None when status == "valid".

        When ``content_sha256`` (the real digest of the actual asset bytes) is
        supplied, this also performs genuine cryptographic tamper detection by
        comparing it against the manifest's hard-binding hash assertion
        (c2pa.hash.*) -- a mismatch means the asset bytes do not match what
        the manifest claims, i.e. real, detected tampering.
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

        if not self._verify_signature_block(manifest, signature_block):
            return "invalid", "tampered_signature", spec_version, claim_generator, len(assertions)

        if content_sha256 is not None:
            declared_hash = self._hard_binding_hash(assertions)
            if declared_hash is not None and declared_hash.lower() != content_sha256.strip().lower():
                # Real cryptographic tamper detection: the manifest's hard
                # binding hash does not match the actual asset bytes' digest.
                return "invalid", "tampered_signature", spec_version, claim_generator, len(assertions)

        return "valid", None, spec_version, claim_generator, len(assertions)

    def verify_manifest(
        self,
        org_id: uuid.UUID,
        content_identifier: str,
        manifest: dict,
        actor_id: uuid.UUID | None,
        content_sha256: str | None = None,
    ) -> ContentProvenanceRecord:
        (
            status_value,
            reason,
            spec_version_detected,
            claim_generator,
            assertion_count,
        ) = self._validate_c2pa_structure(manifest, content_sha256)

        hard_binding_present = isinstance(manifest, dict) and isinstance(manifest.get("assertions"), list) and (
            self._hard_binding_hash(manifest["assertions"]) is not None
        )
        content_hash_verified = bool(content_sha256) and hard_binding_present

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
                # Whether this verification actually performed real
                # cryptographic hard-binding hash comparison against the
                # asset's bytes, vs. a shape-only check of the manifest JSON.
                "content_hash_verified": content_hash_verified,
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

    def get_history(self, org_id: uuid.UUID, content_identifier: str) -> tuple[list[ContentProvenanceRecord], bool]:
        rows = self.db.execute(
            select(ContentProvenanceRecord)
            .where(
                ContentProvenanceRecord.organization_id == org_id,
                ContentProvenanceRecord.content_identifier == content_identifier,
                ContentProvenanceRecord.deleted_at.is_(None),
            )
            .order_by(ContentProvenanceRecord.verified_at.desc(), ContentProvenanceRecord.created_at.desc())
        ).scalars().all()
        if not rows:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No verification history for this content_identifier")

        latest = rows[0]
        drift = any(
            row.claim_generator != latest.claim_generator or row.spec_version_detected != latest.spec_version_detected
            for row in rows[1:]
        )
        return rows, drift
