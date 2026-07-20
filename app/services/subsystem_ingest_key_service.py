"""Per-(organization, subsystem) inbound machine-ingest key registry.

Replaces the previous arrangement where PAM, data-lineage, cookies, consent,
security-ingest and access-monitoring all authenticated their inbound X-CompliVibe-Key
against the SINGLE OpenMetadata/data-lineage integration key (an O(active-orgs)
decrypt-and-compare loop in LineageService.resolve_org_by_api_key). Under that scheme a
key leaked from any one subsystem (e.g. a PAM agent) authenticated all the others for
the same org.

Here each subsystem has its own key, resolved by a direct indexed hash lookup scoped to
a single `key_type`. Modeled on PatentScopedKeyService / carbon_accounting_service:
SHA-256 hash stored (never the raw key), one active key per (org, key_type), raw key
returned once, in-place rotation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subsystem_ingest_key import SUBSYSTEM_KEY_TYPES, SubsystemIngestKey


class SubsystemIngestKeyService:
    VALID_KEY_TYPES = frozenset(SUBSYSTEM_KEY_TYPES)

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _validate_key_type(self, key_type: str) -> None:
        if key_type not in self.VALID_KEY_TYPES:
            raise ValueError(f"invalid subsystem key_type {key_type!r}")

    def provision_key(
        self,
        org_id: uuid.UUID,
        key_type: str,
        created_by_user_id: uuid.UUID | None,
        raw_key: str | None = None,
    ) -> str:
        """Create or rotate the org's key for `key_type`. Returns the RAW key once
        (only its SHA-256 hash is stored; the raw value is never shown again).

        `raw_key` lets a caller supply a specific value (e.g. configure_openmetadata,
        which accepts an operator-provided ingest key); omit it to mint a random one.
        """
        self._validate_key_type(key_type)
        raw_key = raw_key or secrets.token_urlsafe(32)
        key_hash = self.hash_key(raw_key)
        row = self.db.execute(
            select(SubsystemIngestKey).where(
                SubsystemIngestKey.organization_id == org_id,
                SubsystemIngestKey.key_type == key_type,
            )
        ).scalar_one_or_none()
        if row is None:
            self.db.add(
                SubsystemIngestKey(
                    organization_id=org_id,
                    key_type=key_type,
                    api_key_hash=key_hash,
                    is_active=True,
                    created_by_user_id=created_by_user_id,
                )
            )
        else:
            row.api_key_hash = key_hash
            row.is_active = True
            row.rotated_at = datetime.now(UTC)
        self.db.flush()
        return raw_key

    def resolve_org_by_key(self, raw_key: str, key_type: str) -> uuid.UUID | None:
        """Return the org id for an active key of exactly `key_type`, else None.

        Direct indexed lookup on the key hash (not the old O(active-orgs) loop). The
        result is confirmed with a constant-time digest comparison so a match cannot
        be inferred from timing, and it is scoped to a single key_type so a key minted
        for one subsystem never resolves another.
        """
        self._validate_key_type(key_type)
        if not raw_key:
            return None
        key_hash = self.hash_key(raw_key)
        row = self.db.execute(
            select(SubsystemIngestKey).where(
                SubsystemIngestKey.api_key_hash == key_hash,
                SubsystemIngestKey.key_type == key_type,
                SubsystemIngestKey.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None or not hmac.compare_digest(row.api_key_hash, key_hash):
            return None
        return row.organization_id

    def require_org_by_key(self, raw_key: str, key_type: str) -> uuid.UUID:
        """resolve_org_by_key, raising 401 when the key is absent/invalid for this
        subsystem. This is the single inbound-auth entrypoint every subsystem calls."""
        org_id = self.resolve_org_by_key(raw_key, key_type)
        if org_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return org_id

    def list_provisioned_key_types(self, org_id: uuid.UUID) -> list[str]:
        """Which subsystems have an active key for this org (no secret material)."""
        rows = self.db.execute(
            select(SubsystemIngestKey.key_type).where(
                SubsystemIngestKey.organization_id == org_id,
                SubsystemIngestKey.is_active.is_(True),
            )
        ).scalars().all()
        return sorted(rows)
