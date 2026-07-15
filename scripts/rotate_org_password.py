"""Rotate the login password for every user in an organization.

Generalized from the original PulseHealth-specific rotation into reusable ops
tooling for any org. Reads DATABASE_URL from the process environment (production
uses /etc/complivibe/backend.env), so run it with that env loaded, e.g.:

    set -a && source /etc/complivibe/backend.env && set +a
    .venv/bin/python scripts/rotate_org_password.py pulsehealth

The new password is taken from ORG_NEW_PASSWORD if set, otherwise a strong random
one is generated. Only users who are members of the given org are touched; nothing
is deleted. Structurally idempotent (safe to re-run), but note that each run
WITHOUT an explicit ORG_NEW_PASSWORD sets a brand-new random password.

Safety:
  * The plaintext password is revealed only on an interactive TTY, or when --print
    is passed explicitly -- so a generated password can never silently land in a
    log file if this is ever run non-interactively (cron/systemd).
  * As a corollary, the script REFUSES to commit a *generated* password it cannot
    show (no TTY and no --print), rather than rotate users to a value nobody knows
    and lock them out. Pass --print or set ORG_NEW_PASSWORD to a known value.
  * --dry-run reports which users would be rotated without writing anything.
"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.organization import Organization
from app.models.user import User
from app.models.membership import Membership


def _strong_password() -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(20))
    return f"Rotate!{core}#26"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate the login password for all members of an organization."
    )
    parser.add_argument("org_slug", help="Organization slug to rotate (e.g. 'pulsehealth').")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which users would be rotated, without changing anything.",
    )
    parser.add_argument(
        "--print",
        dest="force_print",
        action="store_true",
        help="Print the new plaintext password even when stdout is not a TTY.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    db_url = os.environ["DATABASE_URL"]

    explicit_pw = os.environ.get("ORG_NEW_PASSWORD")
    new_password = explicit_pw or _strong_password()
    generated = explicit_pw is None
    can_reveal = args.force_print or sys.stdout.isatty()

    # Never commit a generated password we can't show -- that would lock users out
    # of accounts whose new password is unknowable. Fail before touching the DB.
    if not args.dry_run and generated and not can_reveal:
        raise SystemExit(
            "Refusing to rotate to a generated password that cannot be shown "
            "(stdout is not a TTY and --print was not given). Re-run with --print, "
            "or set ORG_NEW_PASSWORD to a known value."
        )

    engine = create_engine(db_url)
    with Session(engine) as db:
        org = db.execute(
            select(Organization).where(Organization.slug == args.org_slug)
        ).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"Org (slug={args.org_slug!r}) not found — nothing to do.")

        user_ids = db.execute(
            select(Membership.user_id).where(Membership.organization_id == org.id)
        ).scalars().all()
        users = db.execute(
            select(User).where(User.id.in_(user_ids))
        ).scalars().all()

        if args.dry_run:
            print(f"[dry-run] Would rotate {len(users)} users in org '{args.org_slug}':")
            for email in sorted(u.email for u in users):
                print(f"  - {email}")
            print("[dry-run] No changes written.")
            return

        hashed = get_password_hash(new_password)
        rotated = []
        for u in users:
            u.hashed_password = hashed
            rotated.append(u.email)
        db.commit()

    print(f"Rotated {len(rotated)} '{args.org_slug}' users to a new password.")
    for email in sorted(rotated):
        print(f"  - {email}")

    if can_reveal:
        print(f"\nNew password: {new_password}")
        print("Record this now — it is not stored anywhere else.")
    else:
        # Only reachable when the operator supplied ORG_NEW_PASSWORD (a value they
        # already know), so there is nothing to reveal and nothing is lost.
        print(
            "\n[New password not printed: stdout is not a TTY. It matches the "
            "ORG_NEW_PASSWORD you supplied.]",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
