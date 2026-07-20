#!/usr/bin/env python3
"""Re-issue per-subsystem inbound ingest keys (migration 0317).

Before 0317, PAM, data-lineage, cookies, consent, security-ingest and
access-monitoring all authenticated their inbound X-CompliVibe-Key against ONE shared
key (the OpenMetadata/data-lineage integration key). 0317 gives each subsystem its own
key. The old shared key's raw value is unrecoverable (only its hash was stored), so new
keys MUST be minted and distributed to the agents/scripts that push data.

This script mints all six subsystem keys for every org that currently has an active
OpenMetadata integration (the set that was using the shared inbound key) and prints the
raw keys ONCE so an operator can distribute them securely.

Usage (dry run first):
    python -m scripts.reissue_subsystem_ingest_keys --dry-run
    python -m scripts.reissue_subsystem_ingest_keys --apply > /secure/reissued_keys.txt

Scope to specific orgs:
    python -m scripts.reissue_subsystem_ingest_keys --apply --org <uuid> [--org <uuid> ...]

The raw keys are secrets: capture stdout to a protected file, distribute over a secure
channel, then delete it. Re-running rotates the keys again (old ones stop working).
"""

from __future__ import annotations

import argparse
import sys
import uuid

from sqlalchemy import select

from app.db.session import get_session_maker
from app.models.openmetadata_integration import OpenMetadataIntegration
from app.models.subsystem_ingest_key import SUBSYSTEM_KEY_TYPES
from app.services.subsystem_ingest_key_service import SubsystemIngestKeyService


def _target_org_ids(db, explicit: list[str]) -> list[uuid.UUID]:
    if explicit:
        return [uuid.UUID(o) for o in explicit]
    rows = db.execute(
        select(OpenMetadataIntegration.organization_id).where(OpenMetadataIntegration.is_active.is_(True))
    ).scalars().all()
    # Distinct, one row per org even if duplicates ever existed.
    return sorted(set(rows), key=str)


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-issue per-subsystem inbound ingest keys (migration 0317).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="List target orgs; mint nothing.")
    group.add_argument("--apply", action="store_true", help="Mint and print new keys.")
    parser.add_argument("--org", action="append", default=[], help="Restrict to specific org id(s).")
    args = parser.parse_args()

    session_maker = get_session_maker()
    db = session_maker()
    try:
        org_ids = _target_org_ids(db, args.org)
        if not org_ids:
            print("No target orgs (no active OpenMetadata integration and no --org given).", file=sys.stderr)
            return 0

        if args.dry_run:
            print(f"# DRY RUN: would re-issue {len(SUBSYSTEM_KEY_TYPES)} keys for {len(org_ids)} org(s):", file=sys.stderr)
            for org_id in org_ids:
                print(f"#   {org_id}", file=sys.stderr)
            return 0

        service = SubsystemIngestKeyService(db)
        print("# organization_id\tkey_type\tapi_key  (distribute securely, then delete this output)")
        for org_id in org_ids:
            for key_type in SUBSYSTEM_KEY_TYPES:
                raw_key = service.provision_key(org_id, key_type, created_by_user_id=None)
                print(f"{org_id}\t{key_type}\t{raw_key}")
        db.commit()
        print(f"# Re-issued keys for {len(org_ids)} org(s).", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
