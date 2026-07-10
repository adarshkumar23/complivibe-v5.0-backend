"""add pgvector extension

Revision ID: 0122_add_pgvector_extension
Revises: 0121_ai_content_drafting
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0122_add_pgvector_extension"
down_revision: str | None = "0121_ai_content_drafting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).scalar()
    if not available:
        return
    # The DB role may lack CREATE EXTENSION privilege (e.g. managed Postgres
    # where only a DBA/superuser can install extensions). Scope the attempt to
    # a savepoint so a permission failure doesn't abort the whole migration
    # transaction -- this stays a graceful no-op, matching the fallback
    # (embedding_json text column) used everywhere the vector type isn't live.
    try:
        with bind.begin_nested():
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass


def downgrade() -> None:
    bind = op.get_bind()
    installed = bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if installed:
        op.execute("DROP EXTENSION IF EXISTS vector")
