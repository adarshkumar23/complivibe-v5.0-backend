"""add import parity tracking table for m2

Revision ID: 0247_import_parity_m2
Revises: 0246_import_jobs_m1
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0247_import_parity_m2"
down_revision: str | None = "0246_import_jobs_m1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_parity_tracking",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parity_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"),
        sa.Column("tool_source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('control', 'evidence', 'policy', 'business_unit')",
            name="ck_import_parity_tracking_entity_type",
        ),
        sa.CheckConstraint("imported_count >= 0", name="ck_import_parity_tracking_imported_count"),
        sa.CheckConstraint("verified_count >= 0", name="ck_import_parity_tracking_verified_count"),
        sa.CheckConstraint("parity_pct >= 0 AND parity_pct <= 100", name="ck_import_parity_tracking_parity_pct"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "tool_source",
            name="uq_import_parity_tracking_org_entity_tool",
        ),
    )
    op.create_index(
        "ix_import_parity_tracking_org_tool",
        "import_parity_tracking",
        ["organization_id", "tool_source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_parity_tracking_organization_id"),
        "import_parity_tracking",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_import_parity_tracking_organization_id"), table_name="import_parity_tracking")
    op.drop_index("ix_import_parity_tracking_org_tool", table_name="import_parity_tracking")
    op.drop_table("import_parity_tracking")
