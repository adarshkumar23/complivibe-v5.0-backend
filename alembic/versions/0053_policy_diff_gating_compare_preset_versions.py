"""policy diff gating compare preset versions

Revision ID: 0053_policy_diff_gating_compare_preset_versions
Revises: 0052_policy_diff_gating_compare_presets
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0053_policy_diff_gating_compare_preset_versions"
down_revision: str | None = "0052_policy_diff_gating_compare_presets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["ai_system_governance_policy_diff_gating_compare_presets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3_e68d8871",
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_ver_org_preset",
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_ver_org_status",
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_ver_org_preset_num",
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        ["organization_id", "preset_id", "version_number"],
        unique=False,
    )

    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_active_version_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_active_ver",
        "ai_system_governance_policy_diff_gating_compare_presets",
        ["organization_id", "active_version_id"],
        unique=False,
    )

    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_preset_reports",
        sa.Column("preset_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_preset_reports",
        sa.Column("preset_version_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_preset_reports",
        sa.Column("preset_snapshot_json", sa.JSON(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_policy_diff_gating_cmp_preset_rep_version_id",
        "ai_system_governance_policy_diff_gating_compare_preset_reports",
        "ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
        ["preset_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_version",
        "ai_system_governance_policy_diff_gating_compare_preset_reports",
        ["organization_id", "preset_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_version",
        table_name="ai_system_governance_policy_diff_gating_compare_preset_reports",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_policy_diff_gating_cmp_preset_rep_version_id",
        "ai_system_governance_policy_diff_gating_compare_preset_reports",
        type_="foreignkey",
    )
    op.drop_column("ai_system_governance_policy_diff_gating_compare_preset_reports", "preset_snapshot_json")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_preset_reports", "preset_version_number")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_preset_reports", "preset_version_id")

    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_active_ver",
        table_name="ai_system_governance_policy_diff_gating_compare_presets",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_active_version_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "active_version_id")

    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_ver_org_preset_num",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_ver_org_status",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_ver_org_preset",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
    )
    op.drop_index(
        "ix_ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3_e68d8871",
        table_name="ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b",
    )
    op.drop_table("ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b")
