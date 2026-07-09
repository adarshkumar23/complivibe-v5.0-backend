"""Backfill org_email_configs rows written by the (fixed) Admin Email Config
path onto the canonical `use_platform_ses`/`aws_*_enc`/`from_email` columns.

`OrgEmailConfig` (table `org_email_configs`) is shared by two API surfaces:
`/api/v1/admin/email-config` (`app/api/v1/admin_email_config.py`, backed by
`app/privacy/services/email_config_service.py`) and `/api/v1/email-config`
(`app/platform/routers/email_config.py`). Both write to the same row (keyed
by `organization_id`), but historically only the Admin Email Config path's
writes went into the legacy `config_json` blob without ever flipping
`use_platform_ses` to False. The real send path
(`SESService._resolve_client`) only honors a custom sender when
`use_platform_ses` is False, so any org that configured email exclusively
through `/api/v1/admin/email-config` had its configuration silently ignored
-- production email continued to go out from the platform's default sender.

The application code has been fixed so new writes through either endpoint
populate the same canonical columns. This migration backfills existing rows
that still have `use_platform_ses = true` (the default) but a real
(non-empty-object) `config_json` payload, by decrypting it with the same
Fernet scheme `EmailConfigService` uses and re-encrypting the credentials
with the same scheme `SESService` uses for `aws_access_key_id_enc` /
`aws_secret_key_enc`, so those orgs' previously-inert configuration becomes
live without requiring anyone to re-enter credentials.

Revision ID: 0201_backfill_admin_email_config_unification
Revises: 0200_backfill_ai_risk_assessment_unification
Create Date: 2026-07-09 00:05:00.000000
"""

import base64
import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet

# revision identifiers, used by Alembic.
revision: str = "0201_backfill_admin_email_config_unification"
down_revision: str | None = "0200_backfill_ai_risk_assessment_unification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fernet_from(raw_key: str) -> Fernet:
    raw = (raw_key or "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8"))
        except Exception:
            pass
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def upgrade() -> None:
    from app.core.config import get_settings

    settings = get_settings()

    # Matches app/privacy/services/email_config_service.py::EmailConfigService._fernet
    email_config_key = getattr(settings, "EMAIL_CONFIG_ENCRYPTION_KEY", None) or settings.SECRET_KEY
    legacy_fernet = _fernet_from(email_config_key)

    # Matches app/platform/services/ses_service.py::SESService._resolve_fernet_key
    ses_key = (settings.FERNET_SECRET_KEY or "").strip()
    if ses_key:
        canonical_fernet = Fernet(ses_key.encode("utf-8"))
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        canonical_fernet = Fernet(base64.urlsafe_b64encode(digest))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, config_json
            FROM org_email_configs
            WHERE use_platform_ses = true
              AND config_json IS NOT NULL
              AND config_json <> ''
              AND config_json <> '{}'
            """
        )
    ).fetchall()

    migrated = 0
    for row_id, config_json in rows:
        try:
            decrypted = json.loads(legacy_fernet.decrypt(config_json.encode("utf-8")).decode("utf-8"))
        except Exception:
            # Not decryptable with the legacy key (e.g. already migrated by a
            # differently-keyed environment, or corrupt) -- leave untouched.
            continue

        access_key = decrypted.get("aws_access_key_id")
        secret_key = decrypted.get("aws_secret_access_key")
        region = decrypted.get("region") or "ap-south-1"
        from_address = decrypted.get("from_address")
        if not access_key or not secret_key or not from_address:
            continue

        access_key_enc = canonical_fernet.encrypt(access_key.encode("utf-8")).decode("utf-8")
        secret_key_enc = canonical_fernet.encrypt(secret_key.encode("utf-8")).decode("utf-8")

        bind.execute(
            sa.text(
                """
                UPDATE org_email_configs
                SET use_platform_ses = false,
                    aws_access_key_id_enc = :access_key_enc,
                    aws_secret_key_enc = :secret_key_enc,
                    aws_region = :region,
                    from_email = COALESCE(from_email, :from_email),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "access_key_enc": access_key_enc,
                "secret_key_enc": secret_key_enc,
                "region": region,
                "from_email": from_address,
                "id": row_id,
            },
        )
        migrated += 1

    if migrated:
        print(f"0201: migrated {migrated} org_email_configs row(s) from legacy config_json onto canonical columns")


def downgrade() -> None:
    # Not reversible: we cannot tell which rows were flipped by this
    # migration versus configured directly through /api/v1/email-config.
    pass
