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
    if available:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    bind = op.get_bind()
    installed = bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if installed:
        op.execute("DROP EXTENSION IF EXISTS vector")
