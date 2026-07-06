"""add competitor pricing versioned comparison tables

Revision ID: 0249_competitor_pricing_p1b
Revises: fix_audit_eng_source_sched
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0249_competitor_pricing_p1b"
down_revision: str | None = "0248_evidence_original_m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_pricing_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_competitor_pricing_versions_published_at", "competitor_pricing_versions", ["published_at"], unique=False)
    op.create_index(
        "ix_competitor_pricing_versions_last_updated",
        "competitor_pricing_versions",
        ["last_updated"],
        unique=False,
    )

    op.create_table(
        "competitor_pricing_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("competitor_key", sa.String(length=32), nullable=False),
        sa.Column("competitor_name", sa.String(length=64), nullable=False),
        sa.Column("pricing_model", sa.String(length=32), nullable=False),
        sa.Column("public_pricing_available", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pricing_summary", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("starting_price_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("starting_price_unit", sa.String(length=32), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.ForeignKeyConstraint(["version_id"], ["competitor_pricing_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "competitor_key", name="uq_competitor_pricing_entries_version_key"),
        sa.CheckConstraint(
            "competitor_key IN ('vanta', 'drata', 'sprinto', 'scrut', 'onetrust', 'credo_ai')",
            name="ck_competitor_pricing_entries_competitor_key",
        ),
        sa.CheckConstraint(
            "pricing_model IN ('contact_sales', 'tiered_quote', 'starting_from', 'custom_package')",
            name="ck_competitor_pricing_entries_pricing_model",
        ),
    )
    op.create_index("ix_competitor_pricing_entries_version_id", "competitor_pricing_entries", ["version_id"], unique=False)
    op.create_index("ix_competitor_pricing_entries_competitor_key", "competitor_pricing_entries", ["competitor_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_competitor_pricing_entries_competitor_key", table_name="competitor_pricing_entries")
    op.drop_index("ix_competitor_pricing_entries_version_id", table_name="competitor_pricing_entries")
    op.drop_table("competitor_pricing_entries")
    op.drop_index("ix_competitor_pricing_versions_last_updated", table_name="competitor_pricing_versions")
    op.drop_index("ix_competitor_pricing_versions_published_at", table_name="competitor_pricing_versions")
    op.drop_table("competitor_pricing_versions")
