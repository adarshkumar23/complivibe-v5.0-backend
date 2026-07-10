"""semantic mapping

Revision ID: 0171_semantic_mapping
Revises: 0170_atlas_techniques
Create Date: 2026-06-29 11:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0171_semantic_mapping"
down_revision: str | None = "0170_atlas_techniques"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


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
        # transaction (and every migration after it in the same run).
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
    inspector = sa.inspect(bind)

    has_pgvector = _pgvector_available(bind)

    if _has_table(inspector, "obligations"):
        if has_pgvector and not _has_column(inspector, "obligations", "embedding"):
            op.execute("ALTER TABLE obligations ADD COLUMN embedding vector(384)")
        if not has_pgvector and not _has_column(inspector, "obligations", "embedding_json"):
            op.add_column("obligations", sa.Column("embedding_json", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    if has_pgvector and _has_table(inspector, "obligations") and not _has_index(
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
    if _has_table(inspector, "cross_framework_obligation_mappings"):
        if not _has_column(inspector, "cross_framework_obligation_mappings", "semantic_similarity_score"):
            op.add_column(
                "cross_framework_obligation_mappings",
                sa.Column("semantic_similarity_score", sa.Float(), nullable=True),
            )
        if not _has_column(inspector, "cross_framework_obligation_mappings", "mapping_method"):
            op.add_column(
                "cross_framework_obligation_mappings",
                sa.Column("mapping_method", sa.VARCHAR(length=20), nullable=True),
            )

        op.execute(
            sa.text(
                """
                UPDATE cross_framework_obligation_mappings
                SET mapping_method = 'manual'
                WHERE mapping_method IS NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "cross_framework_obligation_mappings"):
        if _has_column(inspector, "cross_framework_obligation_mappings", "mapping_method"):
            op.drop_column("cross_framework_obligation_mappings", "mapping_method")
        if _has_column(inspector, "cross_framework_obligation_mappings", "semantic_similarity_score"):
            op.drop_column("cross_framework_obligation_mappings", "semantic_similarity_score")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "obligations"):
        if _has_index(inspector, "obligations", "ix_obligation_embedding_hnsw"):
            op.drop_index("ix_obligation_embedding_hnsw", table_name="obligations")

        if _has_column(inspector, "obligations", "embedding"):
            op.execute("ALTER TABLE obligations DROP COLUMN embedding")
        if _has_column(inspector, "obligations", "embedding_json"):
            op.drop_column("obligations", "embedding_json")
