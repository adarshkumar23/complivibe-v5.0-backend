"""Scoped API-key registry for the P2 satellite endpoints.

Replaces P2's in-memory plaintext dev dict (dependencies._DEV_SCOPED_KEYS) with
a real, hash-stored, rotatable key table -- modeled exactly on
CarbonAccountingApiKey / carbon_accounting_service (SHA-256 hash, one key per
(org, key_type), raw key returned once, in-place rotation).

key_type 'export'     -> scope patent_export:p2:read
key_type 'ingest'     -> scope patent_ingest:p2:write
key_type 'p4_ingest'  -> scope patent_ingest:p4:write

P4 has its own key type rather than sharing P2's: resolve_org_by_key filters on
key_type, so a leaked key for one patent integration cannot authenticate the other.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patent_scoped_key import PatentScopedKey
from app.services.audit_service import AuditService

_VALID_KEY_TYPES = frozenset({"export", "ingest", "p4_ingest", "p9_ingest"})


class PatentScopedKeyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def provision_key(self, org_id: uuid.UUID, key_type: str, created_by_user_id: uuid.UUID | None) -> str:
        """Create or rotate the org's scoped key of `key_type`. Returns the RAW
        key once (never stored, never shown again)."""
        if key_type not in _VALID_KEY_TYPES:
            raise ValueError(f"invalid key_type {key_type!r}")
        raw_key = secrets.token_urlsafe(32)
        key_hash = self.hash_key(raw_key)
        row = self.db.execute(
            select(PatentScopedKey).where(
                PatentScopedKey.organization_id == org_id, PatentScopedKey.key_type == key_type
            )
        ).scalar_one_or_none()
        if row is None:
            row = PatentScopedKey(
                organization_id=org_id,
                key_type=key_type,
                api_key_hash=key_hash,
                is_active=True,
                created_by_user_id=created_by_user_id,
            )
            self.db.add(row)
            action = "patent_scoped_key.provisioned"
            was_active = None
        else:
            action = "patent_scoped_key.rotated"
            was_active = row.is_active
            row.api_key_hash = key_hash
            row.is_active = True
            row.rotated_at = datetime.now(UTC)
        self.db.flush()

        # Same class of credential as SubsystemIngestKey, audited the same way: holding
        # one lets a machine push inbound telemetry for a whole satellite of this org.
        # Minting or rotating one must be attributable (who / when / which org / which
        # satellite). Only the key_type and the row identity are recorded -- never the
        # raw key, and never its hash. The write lives here rather than in a router so
        # that a future provisioning endpoint inherits the trail; there is no such
        # endpoint today, which is exactly how this path came to be unaudited.
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type="patent_scoped_keys",
            organization_id=org_id,
            actor_user_id=created_by_user_id,
            entity_id=row.id,
            before_json={"is_active": was_active} if was_active is not None else {},
            after_json={"is_active": True},
            metadata_json={"key_type": key_type},
        )
        self.db.flush()
        return raw_key

    def resolve_org_by_key(self, raw_key: str, key_type: str) -> uuid.UUID | None:
        """Return the org id for an active key of `key_type`, or None."""
        key_hash = self.hash_key(raw_key)
        row = self.db.execute(
            select(PatentScopedKey).where(
                PatentScopedKey.api_key_hash == key_hash,
                PatentScopedKey.key_type == key_type,
                PatentScopedKey.is_active.is_(True),
            )
        ).scalar_one_or_none()
        return row.organization_id if row is not None else None
