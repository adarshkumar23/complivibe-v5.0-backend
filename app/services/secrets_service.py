"""Secrets encryption compatibility layer: legacy Fernet (read-only) + vault (read/write).

This service is the single place that understands both ciphertext formats
used across the platform's per-feature config encryption (OIDC client
secrets, SES/email credentials, AI provider API keys, MLOps and OpenMetadata
integration configs):

  - Legacy format: a `cryptography.fernet.Fernet` token. Every real-world
    Fernet token begins with "gAAAAA" once base64-encoded (the fixed 0x80
    version byte, followed by a handful of always-zero high-order timestamp
    bits for any date before year ~2109), so that prefix is used to detect it.
  - New format: an OpenBao/Vault `transit` engine ciphertext, which always
    begins with "vault:v<key_version>:" per the transit engine's own wire
    format.

New writes always go through vault (`encrypt`). Reads (`decrypt`) accept
either format transparently, so existing rows keep working until the
migration script (scripts/migrate_secrets_to_vault.py) re-encrypts them.

Every encrypt/decrypt call is audit-logged (who/when/which secret/success or
failure) via AuditService, action `secret.encrypt` / `secret.decrypt`,
entity_type `secret`. The audit metadata never contains plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import hvac
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.audit_service import AuditService

_VAULT_PREFIX = "vault:"
_LEGACY_FERNET_PREFIX = "gAAAAA"

LegacyKeyResolver = Callable[[], bytes]


class SecretFormatError(ValueError):
    """The stored ciphertext doesn't match any known format (vault or legacy Fernet)."""


class SecretsBackendError(RuntimeError):
    """The vault/OpenBao transit backend is unreachable, misconfigured, or returned an error."""


def legacy_key_from_fernet_secret_key() -> bytes:
    """Matches OIDCConfigService/SESService/AIProviderService's original derivation:
    use FERNET_SECRET_KEY raw (as-is) if set, else SHA-256(SECRET_KEY)."""
    settings = get_settings()
    raw = (settings.FERNET_SECRET_KEY or "").strip()
    if raw:
        return raw.encode("utf-8")
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def legacy_key_from_named_setting(setting_name: str) -> LegacyKeyResolver:
    """Matches EmailConfigService/LineageService/adapter_factory's original derivation:
    always SHA-256-hash whichever of (the named setting, SECRET_KEY) is set."""

    def _resolve() -> bytes:
        settings = get_settings()
        key_value = getattr(settings, setting_name, None) or settings.SECRET_KEY
        digest = hashlib.sha256(key_value.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    return _resolve


@lru_cache(maxsize=1)
def _vault_client_for(vault_addr: str, vault_token: str) -> hvac.Client:
    settings = get_settings()
    return hvac.Client(
        url=vault_addr,
        token=vault_token,
        timeout=settings.VAULT_REQUEST_TIMEOUT_SECONDS,
    )


class SecretsService:
    """Per-request/per-call service: encrypt() always writes via vault; decrypt()
    detects and handles both vault and legacy-Fernet ciphertexts.

    `legacy_key_resolver` must match the exact derivation used by the
    call-site being migrated (see legacy_key_from_fernet_secret_key /
    legacy_key_from_named_setting above) so that pre-existing ciphertexts for
    that call-site continue to decrypt correctly.
    """

    def __init__(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        legacy_key_resolver: LegacyKeyResolver = legacy_key_from_fernet_secret_key,
    ) -> None:
        self.db = db
        self.organization_id = organization_id
        self.actor_user_id = actor_user_id
        self._legacy_key_resolver = legacy_key_resolver

    @staticmethod
    def is_vault_format(value: str) -> bool:
        return value.startswith(_VAULT_PREFIX)

    @staticmethod
    def is_legacy_fernet_format(value: str) -> bool:
        return value.startswith(_LEGACY_FERNET_PREFIX)

    def _client(self) -> hvac.Client:
        settings = get_settings()
        if not settings.VAULT_ADDR:
            raise SecretsBackendError(
                "Secrets vault backend is not configured (VAULT_ADDR is unset). "
                "Set VAULT_ADDR/VAULT_TOKEN to a running OpenBao/Vault-compatible server."
            )
        return _vault_client_for(settings.VAULT_ADDR, settings.VAULT_TOKEN)

    def encrypt(self, plaintext: str, *, secret_name: str, entity_id: uuid.UUID | None = None) -> str:
        """Encrypt `plaintext` via the vault transit engine. New writes always use vault."""
        settings = get_settings()
        try:
            client = self._client()
            b64_plaintext = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
            response = client.secrets.transit.encrypt_data(
                name=settings.VAULT_TRANSIT_KEY_NAME, plaintext=b64_plaintext
            )
            ciphertext = response["data"]["ciphertext"]
        except SecretsBackendError:
            self._audit("encrypt", secret_name, entity_id, success=False, error="vault_not_configured")
            raise
        except Exception as exc:
            self._audit("encrypt", secret_name, entity_id, success=False, error=str(exc))
            raise SecretsBackendError(f"Failed to encrypt secret '{secret_name}' via the vault backend") from exc

        self._audit("encrypt", secret_name, entity_id, success=True, extra={"format": "vault"})
        return ciphertext

    def decrypt(self, ciphertext: str, *, secret_name: str, entity_id: uuid.UUID | None = None) -> str:
        """Decrypt `ciphertext`, detecting vault vs legacy-Fernet format."""
        if self.is_vault_format(ciphertext):
            return self._decrypt_vault(ciphertext, secret_name=secret_name, entity_id=entity_id)
        if self.is_legacy_fernet_format(ciphertext):
            return self._decrypt_legacy_fernet(ciphertext, secret_name=secret_name, entity_id=entity_id)

        self._audit("decrypt", secret_name, entity_id, success=False, error="unrecognized_format")
        raise SecretFormatError(
            f"Secret '{secret_name}' has an unrecognized ciphertext format "
            "(neither a vault transit ciphertext nor a legacy Fernet token)"
        )

    def _decrypt_vault(self, ciphertext: str, *, secret_name: str, entity_id: uuid.UUID | None) -> str:
        settings = get_settings()
        try:
            client = self._client()
            response = client.secrets.transit.decrypt_data(
                name=settings.VAULT_TRANSIT_KEY_NAME, ciphertext=ciphertext
            )
            plaintext = base64.b64decode(response["data"]["plaintext"]).decode("utf-8")
        except SecretsBackendError:
            self._audit("decrypt", secret_name, entity_id, success=False, error="vault_not_configured")
            raise
        except Exception as exc:
            self._audit("decrypt", secret_name, entity_id, success=False, error=str(exc))
            raise SecretsBackendError(f"Failed to decrypt secret '{secret_name}' via the vault backend") from exc

        self._audit("decrypt", secret_name, entity_id, success=True, extra={"format": "vault"})
        return plaintext

    def _decrypt_legacy_fernet(self, ciphertext: str, *, secret_name: str, entity_id: uuid.UUID | None) -> str:
        try:
            fernet = Fernet(self._legacy_key_resolver())
            plaintext = fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            self._audit("decrypt", secret_name, entity_id, success=False, error="invalid_legacy_fernet_token")
            raise SecretFormatError(f"Secret '{secret_name}' is not a valid legacy Fernet token") from exc

        self._audit("decrypt", secret_name, entity_id, success=True, extra={"format": "legacy_fernet"})
        return plaintext

    def reencrypt_if_legacy(
        self, ciphertext: str, *, secret_name: str, entity_id: uuid.UUID | None = None
    ) -> tuple[str, bool]:
        """Idempotent migration primitive: if `ciphertext` is already vault-format,
        returns it unchanged (changed=False). Otherwise decrypts the legacy Fernet
        token and re-encrypts it via vault (changed=True). Safe to call repeatedly."""
        if self.is_vault_format(ciphertext):
            return ciphertext, False
        plaintext = self.decrypt(ciphertext, secret_name=secret_name, entity_id=entity_id)
        new_ciphertext = self.encrypt(plaintext, secret_name=secret_name, entity_id=entity_id)
        return new_ciphertext, True

    def _audit(
        self,
        action: str,
        secret_name: str,
        entity_id: uuid.UUID | None,
        *,
        success: bool,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata: dict[str, Any] = {"secret_name": secret_name, "success": success}
        if error:
            metadata["error"] = error
        if extra:
            metadata.update(extra)
        AuditService(self.db).write_audit_log(
            action=f"secret.{action}",
            entity_type="secret",
            organization_id=self.organization_id,
            actor_user_id=self.actor_user_id,
            entity_id=entity_id,
            metadata_json=metadata,
        )
