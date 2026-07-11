"""obligation embedding_json always present

Revision ID: 0300_obligation_embedding_json_always_present
Revises: 0299_pgvector_backfill
Create Date: 2026-07-11 00:00:00.000000

0171_semantic_mapping only added `obligations.embedding_json` when pgvector was
NOT available at migration time (`if not has_pgvector`). On a database where
pgvector was already installed before 0171 ever ran -- the actual intended
production configuration -- `embedding_json` was never created at all, while
`app/models/obligation.py` unconditionally maps it as an ORM column. Every
query touching `Obligation` then 500s with `UndefinedColumn`.

`ai_systems.description_embedding` avoids this class of bug by always having
its column created (0123_ai_governance_inventory_shadow_usecases), varying
only the column's *type* (vector vs. text) by pgvector availability, never
whether the column exists at all. This migration applies the same "always
present" guarantee to `obligations.embedding_json`, independent of the
`obligations.embedding` vector column added by 0171/0299. Both columns can
safely coexist -- `embedding_json` is also reused by seed_service.py as a
generic metadata text field, unrelated to the vector search path, which is
driven entirely through raw SQL against `embedding` and never touches the ORM
attribute.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0300_obligation_embedding_json_always_present"
down_revision: str | None = "0299_pgvector_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("obligations") and not _has_column(inspector, "obligations", "embedding_json"):
        op.add_column("obligations", sa.Column("embedding_json", sa.Text(), nullable=True))


def downgrade() -> None:
    # Intentionally a no-op: dropping embedding_json here could remove a
    # column that 0171's downgrade() also manages, and that other callers
    # (seed_service.py) may have already written real data into. Nothing
    # added by this migration needs its own reversal -- 0171's downgrade
    # already drops embedding_json when it's the one that created it.
    pass
