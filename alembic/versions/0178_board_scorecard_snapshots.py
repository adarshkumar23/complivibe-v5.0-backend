"""board scorecard snapshots

Revision ID: 0178_board_scorecard_snapshots
Revises: 0177_organization_export_settings
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0178_board_scorecard_snapshots"
down_revision: str | None = "0177_organization_export_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "board_scorecard_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_label", sa.String(length=200), nullable=True),
        sa.Column("overall_compliance_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_bsc_snap_org"),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"], ondelete="SET NULL", name="fk_bsc_snap_bu"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="RESTRICT", name="fk_bsc_snap_user"),
        sa.PrimaryKeyConstraint("id", name="pk_bsc_snap"),
    )

    op.create_index(
        "ix_bsc_snap_org_created",
        "board_scorecard_snapshots",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_bsc_snap_org_bu",
        "board_scorecard_snapshots",
        ["organization_id", "business_unit_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bsc_snap_org_bu", table_name="board_scorecard_snapshots")
    op.drop_index("ix_bsc_snap_org_created", table_name="board_scorecard_snapshots")
    op.drop_table("board_scorecard_snapshots")
