import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_system_governance_attestation import AISystemGovernanceAttestation
from app.models.attestation_token import AttestationToken
from app.models.export_attestation import ExportAttestation
from app.models.export_job import ExportJob
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_LINKED_ENTITY_TYPES = {"export_attestation", "export_job", "ai_system_governance_attestation"}
ALLOWED_TOKEN_STATUS = {"active", "revoked", "expired"}
ATTESTATION_TOKEN_SIGNATURE_ALG = "HMAC-SHA256"


class AttestationTokenService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    @staticmethod
    def _b64url_decode(raw: str) -> bytes:
        padding = "=" * ((4 - len(raw) % 4) % 4)
        return base64.urlsafe_b64decode(f"{raw}{padding}".encode("utf-8"))

    @staticmethod
    def canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def scope_checksum(cls, scope_json: dict | None) -> str:
        canonical = cls.canonical_json(scope_json or {}).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _secret() -> bytes:
        return get_settings().SECRET_KEY.encode("utf-8")

    @classmethod
    def _sign(cls, payload_b64: str) -> str:
        return hmac.new(cls._secret(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def _compose_token(cls, claims: dict[str, Any]) -> str:
        payload_b64 = cls._b64url_encode(cls.canonical_json(claims).encode("utf-8"))
        signature = cls._sign(payload_b64)
        return f"{payload_b64}.{signature}"

    @classmethod
    def _parse_and_verify_token(cls, token: str) -> dict[str, Any]:
        payload_b64, sep, signature = token.partition(".")
        if not sep or not payload_b64 or not signature:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")
        expected_sig = cls._sign(payload_b64)
        if not hmac.compare_digest(signature, expected_sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")
        try:
            claims = json.loads(cls._b64url_decode(payload_b64).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token") from exc
        if not isinstance(claims, dict):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")
        return claims

    def _require_linked_entity(self, *, organization_id: uuid.UUID, linked_entity_type: str, linked_entity_id: uuid.UUID) -> None:
        linked_entity_type = validate_choice(linked_entity_type, ALLOWED_LINKED_ENTITY_TYPES, "linked_entity_type", status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)
        if linked_entity_type == "export_attestation":
            row = self.db.execute(
                select(ExportAttestation.id).where(
                    ExportAttestation.organization_id == organization_id,
                    ExportAttestation.id == linked_entity_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked export attestation not found")
            return
        if linked_entity_type == "export_job":
            row = self.db.execute(
                select(ExportJob.id).where(
                    ExportJob.organization_id == organization_id,
                    ExportJob.id == linked_entity_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked export job not found")
            return
        row = self.db.execute(
            select(AISystemGovernanceAttestation.id).where(
                AISystemGovernanceAttestation.organization_id == organization_id,
                AISystemGovernanceAttestation.id == linked_entity_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked AI system governance attestation not found")

    def create_token(
        self,
        *,
        organization_id: uuid.UUID,
        purpose: str,
        scope_json: dict | None,
        linked_entity_type: str,
        linked_entity_id: uuid.UUID,
        expires_at: datetime,
        created_by_user_id: uuid.UUID,
    ) -> tuple[AttestationToken, str]:
        now = self.utcnow()
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="expires_at must be in the future")
        self._require_linked_entity(
            organization_id=organization_id,
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
        )

        token_id = uuid.uuid4()
        normalized_scope = scope_json or {}
        scope_checksum = self.scope_checksum(normalized_scope)
        claims = {
            "tid": str(token_id),
            "org": str(organization_id),
            "purpose": purpose,
            "scope_checksum_sha256": scope_checksum,
            "linked_entity_type": linked_entity_type,
            "linked_entity_id": str(linked_entity_id),
            "exp": int(expires_at.timestamp()),
            "nonce": secrets.token_urlsafe(12),
            "alg": ATTESTATION_TOKEN_SIGNATURE_ALG,
        }
        plaintext_token = self._compose_token(claims)
        row = AttestationToken(
            id=token_id,
            organization_id=organization_id,
            token_hash=self.hash_token(plaintext_token),
            purpose=purpose,
            scope_json=normalized_scope,
            scope_checksum_sha256=scope_checksum,
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
            expires_at=expires_at,
            status="active",
            validation_count=0,
            last_validated_at=None,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation_token.created",
            entity_type="attestation_token",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=created_by_user_id,
            after_json={
                "purpose": row.purpose,
                "linked_entity_type": row.linked_entity_type,
                "linked_entity_id": str(row.linked_entity_id),
                "expires_at": row.expires_at.isoformat(),
            },
            metadata_json={"source": "api"},
        )
        return row, plaintext_token

    def require_token(self, *, organization_id: uuid.UUID, token_id: uuid.UUID) -> AttestationToken:
        row = self.db.execute(
            select(AttestationToken).where(
                AttestationToken.organization_id == organization_id,
                AttestationToken.id == token_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation token not found")
        return row

    def revoke_token(
        self,
        *,
        organization_id: uuid.UUID,
        token_id: uuid.UUID,
        reason: str | None,
        actor_user_id: uuid.UUID,
    ) -> AttestationToken:
        # The token system has no other way to invalidate a token before its
        # natural expiry -- if a plaintext token leaks (logs, a compromised
        # integration, etc.) there was previously no way to stop it validating
        # successfully until expires_at. Revocation is checked by validate_token
        # via `status != "active"`, so setting status here is sufficient to
        # immediately deny every future validation.
        row = self.require_token(organization_id=organization_id, token_id=token_id)
        if row.status == "revoked":
            return row
        if row.status == "expired":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Token has already expired")

        before_status = row.status
        row.status = "revoked"
        row.revoked_at = self.utcnow()
        row.revoked_by_user_id = actor_user_id
        row.revocation_reason = reason
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation_token.revoked",
            entity_type="attestation_token",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json={"status": before_status},
            after_json={"status": row.status, "revocation_reason": reason},
            metadata_json={"source": "api"},
        )
        return row

    def validate_token(self, plaintext_token: str) -> AttestationToken:
        claims = self._parse_and_verify_token(plaintext_token)
        token_hash = self.hash_token(plaintext_token)
        row = self.db.execute(select(AttestationToken).where(AttestationToken.token_hash == token_hash)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")

        now = self.utcnow()
        expires_at = row.expires_at if row.expires_at.tzinfo is not None else row.expires_at.replace(tzinfo=UTC)
        if claims.get("exp") != int(expires_at.timestamp()):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")
        if expires_at <= now:
            if row.status != "expired":
                row.status = "expired"
                self.db.flush()
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Attestation token expired")

        row.status = validate_choice(row.status, ALLOWED_TOKEN_STATUS, "attestation token status", status_code=status.HTTP_401_UNAUTHORIZED)
        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")

        expected_fields = {
            "tid": str(row.id),
            "org": str(row.organization_id),
            "purpose": row.purpose,
            "scope_checksum_sha256": row.scope_checksum_sha256,
            "linked_entity_type": row.linked_entity_type,
            "linked_entity_id": str(row.linked_entity_id),
            "alg": ATTESTATION_TOKEN_SIGNATURE_ALG,
        }
        for key, expected in expected_fields.items():
            if str(claims.get(key)) != expected:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid attestation token")

        self._require_linked_entity(
            organization_id=row.organization_id,
            linked_entity_type=row.linked_entity_type,
            linked_entity_id=row.linked_entity_id,
        )

        row.validation_count = int(row.validation_count or 0) + 1
        row.last_validated_at = now
        self.db.flush()
        return row
