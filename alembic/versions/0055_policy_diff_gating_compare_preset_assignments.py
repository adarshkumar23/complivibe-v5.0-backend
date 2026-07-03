"""policy diff gating compare preset assignments

Revision ID: 0055_policy_diff_gating_compare_preset_assignments
Revises: 0054_policy_diff_gating_compare_preset_pinning
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0055_policy_diff_gating_compare_preset_assignments"
down_revision: str | None = "0054_policy_diff_gating_compare_preset_pinning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
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
            ["ai_system_governance_policy_diff_gating_compare_presets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba_c506edb4",
        "ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_status",
        "ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_scope",
        "ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
        ["organization_id", "scope_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_preset",
        "ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_priority",
        "ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
        ["organization_id", "priority"],
        unique=False,
    )

    op.create_table(
        "ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_0c2dc1b3",
        "ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_hist_org_assign",
        "ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
        ["organization_id", "assignment_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_hist_org_created",
        "ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_hist_org_created",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_hist_org_assign",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
    )
    op.drop_index(
        "ix_ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_0c2dc1b3",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec",
    )
    op.drop_table("ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec")

    op.drop_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_priority",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_preset",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_scope",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_status",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
    )
    op.drop_index(
        "ix_ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba_c506edb4",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54",
    )
    op.drop_table("ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54")

