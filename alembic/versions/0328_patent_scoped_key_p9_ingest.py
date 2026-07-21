"""patent_scoped_keys: add a distinct p9_ingest key type (patent P9)

Widens ck_patent_scoped_keys_key_type from ('export', 'ingest', 'p4_ingest') to
include 'p9_ingest', so the P9 contract-extraction satellite authenticates with
its OWN key rather than borrowing P2's or P4's.

Why not reuse an existing key type
----------------------------------
Same reasoning as 0326, which gave P4 its own type: migration 0317 exists
precisely because six inbound subsystems once shared one OpenMetadata key, so a
key leaked from any one of them authenticated all the others for that
organisation. Handing P9 an existing patent key would rebuild that hazard a
third time -- a leaked P2 key would let an attacker forge contract obligations,
and a leaked P9 key would let them write into the governance knowledge graph or
push forged monitoring readings.

The exposure is not hypothetical for P9 specifically. A commitment created
through this route becomes a live monitoring rule that fires on real incidents
and notifies real customers, so forging one is a way to manufacture or suppress
a customer-facing breach-notification obligation.

Isolation is enforced by the lookup, not by convention:
PatentScopedKeyService.resolve_org_by_key filters on key_type, so a hash issued
for 'p4_ingest' cannot resolve for 'p9_ingest' even though both live in the same
table.

Naming: the two original values stay unprefixed ('export'/'ingest' mean P2 for
historical reasons -- renaming them would invalidate every key currently issued
to a P2 satellite). New values carry the explicit prefix.

Identifier lengths: ck_patent_scoped_keys_key_type (30). The key_type column is
String(16) and 'p9_ingest' is 9 characters, so the widened vocabulary fits the
existing column with no ALTER of the type.

Revision ID: 0328_patent_scoped_key_p9_ingest
Revises: 0327_p9_contract_obligation_extraction_fields
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0328_patent_scoped_key_p9_ingest"
down_revision: str | None = "0327_p9_contract_obligation_extraction_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "patent_scoped_keys"
CHECK_NAME = "ck_patent_scoped_keys_key_type"

EXISTING_VALUES = ("export", "ingest", "p4_ingest")
NEW_VALUE = "p9_ingest"
ALL_VALUES = EXISTING_VALUES + (NEW_VALUE,)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _set_allowed_values(values: tuple[str, ...]) -> None:
    """PostgreSQL only.

    On SQLite the constraint is inline in the CREATE TABLE and cannot be
    replaced without rebuilding the table; SQLite is only ever the test harness
    here, and the model's own CheckConstraint gives the harness the same
    vocabulary.
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
    """Narrow back to the pre-P9 vocabulary.

    Refuses while any organisation still holds a p9_ingest key. Silently
    deleting or orphaning a live credential to make a schema change fit would
    break that organisation's satellite ingest with no trace of why.
    """
    in_use = op.get_bind().execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE key_type = :value"), {"value": NEW_VALUE}
    ).scalar()
    if in_use:
        raise RuntimeError(
            f"cannot downgrade: {in_use} organisation(s) hold a '{NEW_VALUE}' scoped key. "
            "Deactivate and delete those keys deliberately (they are live credentials for "
            "the P9 contract-extraction satellite) before narrowing the constraint, then re-run."
        )
    _set_allowed_values(EXISTING_VALUES)
