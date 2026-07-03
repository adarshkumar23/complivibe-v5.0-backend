"""diagnostic export diff gating compare preset assignments

Revision ID: 0064_diag_export_diff_gating_compare_preset_assignments
Revises: 0063_diag_export_diff_gating_compare_preset_versions
Create Date: 2026-06-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0064_diag_export_diff_gating_compare_preset_assignments"
down_revision: str | None = "0063_diag_export_diff_gating_compare_preset_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_assi_a9442612",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_65278498",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_6af4dddb",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
        ["organization_id", "scope_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_93fa4c13",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_baf4b87e",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
        ["organization_id", "priority"],
        unique=False,
    )

    op.create_table(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_assi_1ad304d3",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_8b572bad",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
        ["organization_id", "assignment_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_068f8286",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
        ["organization_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_068f8286",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_8b572bad",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
    )
    op.drop_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_assi_1ad304d3",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8",
    )
    op.drop_table("ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_baf4b87e",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_93fa4c13",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_6af4dddb",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_65278498",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
    )
    op.drop_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_assi_a9442612",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb",
    )
    op.drop_table("ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb")
