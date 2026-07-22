"""Grandfather pre-cutover organizations onto the Enterprise plan.

Stage 1c-1 safety step for the Free/Trial/Paid access model. Before any
feature gating (require_feature / require_capacity, Stage 1c-4) is deployed,
every organization that predates the access model must be pinned to a full
plan so gating cannot strip access it has today.

This sets subscription_plan='enterprise', subscription_status='active' for
all organizations created strictly before a cutover timestamp. Enterprise =
every feature flag TRUE + no record caps, so gating becomes a no-op for them.

Safety properties:
  * Read-first: prints the current state of every org before changing anything.
  * Idempotent: an org already on enterprise/active is left unchanged (no-op),
    and re-running the script produces no further changes.
  * Scoped: only touches orgs with created_at < cutover; never newer orgs.
  * Dry-run by default: pass --commit to actually write; otherwise rolls back.

Usage:
  python -m scripts.grandfather_existing_orgs --cutover 2026-07-22T00:00:00Z
  python -m scripts.grandfather_existing_orgs --cutover 2026-07-22T00:00:00Z --commit

NOTE: This is RUN AGAINST PROD as a separate go-live step, only AFTER the
0329 migration + free/trial plan seed are live, and BEFORE the 1c-4 gating
deploy. Do not bundle it into the gating release.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import get_session_maker
from app.models.organization import Organization

TARGET_PLAN = "enterprise"
TARGET_STATUS = "active"


def _parse_cutover(raw: str) -> datetime:
    # Accept ...Z or an explicit offset; normalise to aware UTC.
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grandfather pre-cutover orgs onto Enterprise.")
    parser.add_argument("--cutover", required=True, help="ISO8601 timestamp; orgs created before this are grandfathered.")
    parser.add_argument("--commit", action="store_true", help="Persist changes (default: dry-run, rolls back).")
    args = parser.parse_args()

    cutover = _parse_cutover(args.cutover)
    session = get_session_maker()()
    try:
        orgs = session.execute(
            select(Organization).where(Organization.created_at < cutover).order_by(Organization.created_at)
        ).scalars().all()

        print(f"Cutover: {cutover.isoformat()}  |  pre-cutover orgs: {len(orgs)}")
        print(f"{'name':<28} {'from_plan':<12} {'from_status':<10} -> action")
        changed = 0
        for org in orgs:
            already = org.subscription_plan == TARGET_PLAN and org.subscription_status == TARGET_STATUS
            action = "no-op (already enterprise/active)" if already else f"-> {TARGET_PLAN}/{TARGET_STATUS}"
            print(f"{(org.name or '')[:28]:<28} {org.subscription_plan:<12} {org.subscription_status:<10} {action}")
            if not already:
                org.subscription_plan = TARGET_PLAN
                org.subscription_status = TARGET_STATUS
                changed += 1

        if args.commit:
            session.commit()
            print(f"\nCOMMITTED. Orgs changed: {changed} / {len(orgs)}.")
        else:
            session.rollback()
            print(f"\nDRY-RUN (no changes written). Would change: {changed} / {len(orgs)}. Re-run with --commit to apply.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
