"""pgvector backfill - real vector columns now that the extension is installed

Revision ID: 0299_pgvector_backfill
Revises: 0298_cloud_evidence_connectors
Create Date: 2026-07-10 00:00:00.000000

Migrations 0122/0123/0171 already contain the correct conditional logic to
create real `vector(384)` columns when pgvector is available, but they ran
in environments where the extension was not yet installed, so `obligations`
and `ai_systems` were left with text-based JSON fallback columns
(`embedding_json`, `description_embedding` as text). Now that
`postgresql-16-pgvector` is installed and the `vector` extension is enabled,
this migration adds the real vector columns those tables were always meant
to have. Both fallback columns are empty in every known environment, so no
data migration is needed - this is purely an additive schema fix.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0299_pgvector_backfill"
down_revision: str | None = "0298_cloud_evidence_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _column_type(inspector: sa.Inspector, table_name: str, column_name: str) -> str | None:
    if not inspector.has_table(table_name):
        return None
    for col in inspector.get_columns(table_name):
        if col.get("name") == column_name:
            return str(col.get("type"))
    return None


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _pgvector_available(bind: sa.Connection) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    try:
        available = bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"))
        if available.fetchone() is None:
            return False
        # Scoped to a savepoint: if the role lacks CREATE EXTENSION privilege,
        # this rolls back cleanly instead of aborting the whole migration
        # transaction (see 0122_add_pgvector_extension.py for the same fix).
        try:
            with bind.begin_nested():
                op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            pass
        result = bind.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        return result.fetchone() is not None
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    has_pgvector = _pgvector_available(bind)
    if not has_pgvector:
        return

    inspector = sa.inspect(bind)

    if _has_table(inspector, "obligations") and not _has_column(inspector, "obligations", "embedding"):
        op.execute("ALTER TABLE obligations ADD COLUMN embedding vector(384)")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "obligations") and not _has_index(
        inspector, "obligations", "ix_obligation_embedding_hnsw"
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_obligation_embedding_hnsw
            ON obligations
            USING hnsw (embedding vector_cosine_ops)
            WITH (m=16, ef_construction=64)
            """
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "ai_systems"):
        current_type = _column_type(inspector, "ai_systems", "description_embedding")
        if current_type is not None and "VECTOR" not in current_type.upper():
            op.execute(
                "ALTER TABLE ai_systems "
                "ALTER COLUMN description_embedding TYPE vector(384) USING NULL"
            )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "ai_systems") and not _has_index(
        inspector, "ai_systems", "ix_ai_systems_description_embedding_hnsw"
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_ai_systems_description_embedding_hnsw
            ON ai_systems
            USING hnsw (description_embedding vector_cosine_ops)
            WITH (m=16, ef_construction=64)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)

    if _has_table(inspector, "ai_systems"):
        if _has_index(inspector, "ai_systems", "ix_ai_systems_description_embedding_hnsw"):
            op.drop_index("ix_ai_systems_description_embedding_hnsw", table_name="ai_systems")
        current_type = _column_type(inspector, "ai_systems", "description_embedding")
        if current_type is not None and "VECTOR" in current_type.upper():
            op.execute(
                "ALTER TABLE ai_systems "
                "ALTER COLUMN description_embedding TYPE text USING NULL"
            )

    if _has_table(inspector, "obligations"):
        if _has_index(inspector, "obligations", "ix_obligation_embedding_hnsw"):
            op.drop_index("ix_obligation_embedding_hnsw", table_name="obligations")
        if _has_column(inspector, "obligations", "embedding"):
            op.execute("ALTER TABLE obligations DROP COLUMN embedding")
