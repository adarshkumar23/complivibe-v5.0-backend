"""patent_scoped_keys: add a distinct p4_ingest key type (patent P4)

Widens ck_patent_scoped_keys_key_type from ('export', 'ingest') to include
'p4_ingest', so the P4 monitoring satellite authenticates with its OWN key rather
than borrowing P2's.

Why not reuse P2's 'ingest' key
-------------------------------
Because that is precisely the vulnerability migration 0317 was written to close. Before
0317, six inbound subsystems all authenticated against one shared OpenMetadata key, so a
key leaked from any one of them authenticated all the others for that organisation.
0317 split them one-per-(organization, key_type). Handing P4 the existing
patent_ingest:p2:write key would rebuild that exact hazard across two patent
integrations: a leaked P2 key would let an attacker push forged monitoring readings, and
a leaked P4 key would let them write into the governance knowledge graph.

Isolation is already enforced by the lookup, not by convention:
PatentScopedKeyService.resolve_org_by_key filters on key_type, so a hash issued for
'ingest' cannot resolve for 'p4_ingest' even though both live in the same table.

Naming: the two existing values stay unprefixed. Renaming them to 'p2_export' /
'p2_ingest' would be tidier but would invalidate every key currently issued to a P2
satellite -- a live-credential break for a cosmetic gain. The new value carries the
explicit prefix, and the model documents that unprefixed means P2 for historical
reasons.

Identifier lengths: ck_patent_scoped_keys_key_type (30). The key_type column is
String(16) and 'p4_ingest' is 9 characters, so the widened vocabulary fits the existing
column with no ALTER of the type.

Revision ID: 0326_patent_scoped_key_p4_ingest
Revises: 0325_user_is_system_account
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0326_patent_scoped_key_p4_ingest"
down_revision: str | None = "0325_user_is_system_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "patent_scoped_keys"
CHECK_NAME = "ck_patent_scoped_keys_key_type"

EXISTING_VALUES = ("export", "ingest")
NEW_VALUE = "p4_ingest"
ALL_VALUES = EXISTING_VALUES + (NEW_VALUE,)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _set_allowed_values(values: tuple[str, ...]) -> None:
    """PostgreSQL only.

    On SQLite the constraint is inline in the CREATE TABLE and cannot be replaced
    without rebuilding the table; SQLite is only ever the test harness here, and the
    model's own CheckConstraint gives the harness the same vocabulary.
    """
    if not _is_postgres():
        logger.info(
            "skipping %s on %s (test dialect); the constraint is PostgreSQL-only",
            CHECK_NAME,
            op.get_bind().dialect.name,
        )
        return
    rendered = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CHECK_NAME}"))
    op.create_check_constraint(CHECK_NAME, TABLE, f"key_type IN ({rendered})")


def upgrade() -> None:
    _set_allowed_values(ALL_VALUES)


def downgrade() -> None:
    """Narrow back to P2's two values.

    Refuses while any organisation still holds a p4_ingest key. Silently deleting or
    orphaning a live credential to make a schema change fit would break that
    organisation's satellite ingest with no trace of why.
    """
    in_use = op.get_bind().execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE key_type = :value"), {"value": NEW_VALUE}
    ).scalar()
    if in_use:
        raise RuntimeError(
            f"cannot downgrade: {in_use} organisation(s) hold a '{NEW_VALUE}' scoped key. "
            "Deactivate and delete those keys deliberately (they are live credentials for "
            "the P4 monitoring satellite) before narrowing the constraint, then re-run."
        )
    _set_allowed_values(EXISTING_VALUES)
