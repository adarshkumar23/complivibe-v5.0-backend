"""Re-encrypts every legacy-Fernet secret column to the vault (OpenBao/Infisical
transit engine) format, in place.

Idempotent: any column already in vault format (`vault:v...`) is left
untouched, so running this twice never double-encrypts.

Requires VAULT_ADDR/VAULT_TOKEN (and DATABASE_URL) to already be configured --
see docs/runbooks/secrets_migration_fernet_to_vault.md for the production
procedure. This script itself performs NO production actions; it only acts on
whatever DATABASE_URL/VAULT_ADDR the environment points it at.

Usage:
    python -m scripts.migrate_secrets_to_vault [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session_maker
from app.models.mlops_integration import MLOpsIntegration
from app.models.oidc_config import OIDCConfig
from app.models.openmetadata_integration import OpenMetadataIntegration
from app.models.org_email_config import OrgEmailConfig
from app.models.organization_ai_configuration import OrganizationAIConfiguration
from app.services.secrets_service import (
    SecretFormatError,
    SecretsBackendError,
    SecretsService,
    legacy_key_from_fernet_secret_key,
    legacy_key_from_named_setting,
)


@dataclass
class MigrationStats:
    scanned: int = 0
    migrated: int = 0
    already_vault: int = 0
    empty: int = 0
    errors: list[str] = field(default_factory=list)


def _migrate_column(
    db: Session,
    *,
    row,
    column_name: str,
    secret_name: str,
    legacy_key_resolver,
    stats: MigrationStats,
    dry_run: bool,
) -> None:
    value = getattr(row, column_name)
    if not value:
        stats.empty += 1
        return

    stats.scanned += 1
    secrets = SecretsService(
        db, organization_id=row.organization_id, legacy_key_resolver=legacy_key_resolver
    )
    if secrets.is_vault_format(value):
        stats.already_vault += 1
        return

    try:
        new_value, changed = secrets.reencrypt_if_legacy(value, secret_name=secret_name, entity_id=row.id)
    except (SecretFormatError, SecretsBackendError) as exc:
        stats.errors.append(f"{column_name} on {type(row).__name__}({row.id}): {exc}")
        return

    if changed and not dry_run:
        setattr(row, column_name, new_value)
    if changed:
        stats.migrated += 1


def migrate(db: Session, *, dry_run: bool = False) -> MigrationStats:
    stats = MigrationStats()

    for row in db.execute(select(OIDCConfig)).scalars():
        _migrate_column(
            db,
            row=row,
            column_name="client_secret_enc",
            secret_name="oidc_client_secret",
            legacy_key_resolver=legacy_key_from_fernet_secret_key,
            stats=stats,
            dry_run=dry_run,
        )

    for row in db.execute(select(MLOpsIntegration)).scalars():
        _migrate_column(
            db,
            row=row,
            column_name="config_json",
            secret_name="mlops_integration_config",
            legacy_key_resolver=legacy_key_from_named_setting("MLOPS_CONFIG_ENCRYPTION_KEY"),
            stats=stats,
            dry_run=dry_run,
        )

    for row in db.execute(select(OpenMetadataIntegration)).scalars():
        _migrate_column(
            db,
            row=row,
            column_name="config_json",
            secret_name="openmetadata_integration_config",
            legacy_key_resolver=legacy_key_from_named_setting("OPENMETADATA_CONFIG_ENCRYPTION_KEY"),
            stats=stats,
            dry_run=dry_run,
        )

    for row in db.execute(select(OrganizationAIConfiguration)).scalars():
        for column_name in ("groq_api_key_encrypted", "azure_api_key_encrypted"):
            _migrate_column(
                db,
                row=row,
                column_name=column_name,
                secret_name="ai_provider_credential",
                legacy_key_resolver=legacy_key_from_fernet_secret_key,
                stats=stats,
                dry_run=dry_run,
            )

    for row in db.execute(select(OrgEmailConfig)).scalars():
        _migrate_column(
            db,
            row=row,
            column_name="config_json",
            secret_name="org_email_config",
            legacy_key_resolver=legacy_key_from_named_setting("EMAIL_CONFIG_ENCRYPTION_KEY"),
            stats=stats,
            dry_run=dry_run,
        )
        for column_name in ("aws_access_key_id_enc", "aws_secret_key_enc"):
            _migrate_column(
                db,
                row=row,
                column_name=column_name,
                secret_name="ses_aws_credential",
                legacy_key_resolver=legacy_key_from_fernet_secret_key,
                stats=stats,
                dry_run=dry_run,
            )

    if not dry_run:
        db.commit()
    else:
        db.rollback()

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Scan and report what would change without writing anything"
    )
    args = parser.parse_args()

    session = get_session_maker()()
    try:
        stats = migrate(session, dry_run=args.dry_run)
    finally:
        session.close()

    print(f"legacy secrets scanned:  {stats.scanned}")
    print(f"migrated to vault:       {stats.migrated}")
    print(f"already vault-format:    {stats.already_vault}")
    print(f"empty/skipped columns:   {stats.empty}")
    if stats.errors:
        print(f"errors: {len(stats.errors)}")
        for error in stats.errors:
            print(f"  - {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
