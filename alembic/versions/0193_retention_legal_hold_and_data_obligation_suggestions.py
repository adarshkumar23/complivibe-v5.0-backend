"""retention legal hold and persisted data obligation suggestions

Revision ID: 0193_retention_legal_hold_and_data_obligation_suggestions
Revises: 0192_control_exception_scheduler_common_controls_alignment
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0193_retention_legal_hold_and_data_obligation_suggestions"
down_revision: str | None = "0192_control_exception_scheduler_common_controls_alignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "data_retention_policies",
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "data_obligation_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("data_asset_id", sa.Uuid(), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("obligation_id", sa.Uuid(), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("applied_by", sa.Uuid(), nullable=True),
        sa.Column("dismissed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'dismissed')",
            name="ck_data_obligation_suggestions_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dismissed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_asset_id",
            "obligation_id",
            name="uq_data_obligation_suggestions_asset_obligation",
        ),
    )
    op.create_index(
        "ix_data_obligation_suggestions_org_status",
        "data_obligation_suggestions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_data_obligation_suggestions_org_asset",
        "data_obligation_suggestions",
        ["organization_id", "data_asset_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_obligation_suggestions_org_asset", table_name="data_obligation_suggestions")
    op.drop_index("ix_data_obligation_suggestions_org_status", table_name="data_obligation_suggestions")
    op.drop_table("data_obligation_suggestions")
    op.drop_column("data_retention_policies", "legal_hold")
