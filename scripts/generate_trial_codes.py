"""Generate single-use trial codes for the access model.

Codes are stored HASHED (SHA-256 hex) in trial_codes; the plaintext is written
ONLY to an out-of-band CSV for distribution and is never persisted in the DB or
logged. Each run mints a fresh random batch, so the script is safe to re-run to
add more codes (e.g. a second 1000-batch) -- existing code hashes are never
collided with.

Usage:
  python -m scripts.generate_trial_codes --out /secure/path/codes.csv                 # dry-run (default)
  python -m scripts.generate_trial_codes --out /secure/path/codes.csv --commit         # 1000 codes
  python -m scripts.generate_trial_codes --count 500 --batch-label launch --out ... --commit

NOTE: The real 1000-code production batch is a deliberate go-live step, not part
of the scratch build.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import secrets

from sqlalchemy import select

from app.db.session import get_session_maker
from app.models.trial_code import TrialCode

# Crockford base32 -- excludes I, L, O, U to avoid transcription ambiguity.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _generate_code() -> str:
    groups = ["".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3)]
    return "CV-" + "-".join(groups)  # e.g. CV-7QF2-9KMX-3TB8 (17 chars)


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate single-use trial codes (hashed in DB, plaintext to CSV).")
    parser.add_argument("--count", type=int, default=1000, help="Number of codes to generate (default 1000).")
    parser.add_argument("--out", required=True, help="CSV path for plaintext codes (out-of-band distribution).")
    parser.add_argument("--batch-label", default="default", help="Label recorded on every code in this batch.")
    parser.add_argument("--commit", action="store_true", help="Persist rows + write CSV (default: dry-run).")
    args = parser.parse_args()

    session = get_session_maker()()
    try:
        existing = {h for (h,) in session.execute(select(TrialCode.code_hash)).all()}
        codes: list[str] = []
        seen: set[str] = set()
        while len(codes) < args.count:
            code = _generate_code()
            h = _hash(code)
            if h in existing or h in seen:
                continue  # astronomically rare; regenerate to guarantee uniqueness
            seen.add(h)
            codes.append(code)

        for code in codes:
            session.add(TrialCode(code_hash=_hash(code), code_prefix=code[:7], batch_label=args.batch_label))

        if not args.commit:
            session.rollback()
            print(f"DRY-RUN: would generate {len(codes)} codes (batch='{args.batch_label}'). "
                  f"No DB rows written, no CSV written. Re-run with --commit to apply.")
            return

        session.commit()
        # Write the plaintext CSV only after the hashed rows are safely persisted.
        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["code", "batch_label"])
            for code in codes:
                writer.writerow([code, args.batch_label])

        print(f"Generated {len(codes)} trial codes (batch='{args.batch_label}').")
        print(f"Plaintext codes written to: {args.out}")
        print("DB stores only SHA-256 hashes -- the CSV is the ONLY copy of the plaintext. Distribute securely.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
