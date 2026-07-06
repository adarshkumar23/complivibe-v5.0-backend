"""add original_created_at to evidence items for imported history

Revision ID: 0248_evidence_original_m3
Revises: 0247_import_parity_m2
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0248_evidence_original_m3"
down_revision: str | None = "0247_import_parity_m2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_items", sa.Column("original_created_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE evidence_items
            SET original_created_at = COALESCE(collected_at, created_at)
            WHERE source = 'imported' AND original_created_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "original_created_at")
