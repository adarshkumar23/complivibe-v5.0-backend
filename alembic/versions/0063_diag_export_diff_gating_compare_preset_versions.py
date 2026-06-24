"""diagnostic export diff gating compare preset versions and pinning

Revision ID: 0063_diag_export_diff_gating_compare_preset_versions
Revises: 0062_diagnostic_export_diff_gating_compare_presets
Create Date: 2026-06-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0063_diag_export_diff_gating_compare_preset_versions"
down_revision: str | None = "0062_diagnostic_export_diff_gating_compare_presets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
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
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["ai_system_governance_diagnostic_export_diff_gating_compare_presets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_versions_organization_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_ver_org_preset",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_ver_org_status",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_ver_org_preset_num",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["organization_id", "preset_id", "version_number"],
        unique=False,
    )

    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("pinned_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column(
            "version_selection_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active_then_mutable'"),
        ),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column(
            "allow_explicit_version_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("pinned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("pin_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("unpinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("unpinned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        sa.Column("unpin_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_active_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pinned_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["pinned_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pinned_by_user_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        "users",
        ["pinned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_unpinned_by_user_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        "users",
        ["unpinned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_active_ver",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        ["organization_id", "active_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_pinned_ver",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        ["organization_id", "pinned_version_id"],
        unique=False,
    )

    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column("preset_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column("preset_version_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column("preset_snapshot_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column("version_resolution_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column("pinned_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column(
            "explicit_version_override_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        sa.Column("version_override_reason", sa.String(length=2000), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["preset_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_pinned_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
        ["pinned_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_version",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "preset_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_version",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_pinned_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        type_="foreignkey",
    )
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "version_override_reason")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "explicit_version_override_used")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "pinned_version_id")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "version_resolution_source")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "preset_snapshot_json")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "preset_version_number")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports", "preset_version_id")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_pinned_ver",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_presets",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_active_ver",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_presets",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_unpinned_by_user_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pinned_by_user_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pinned_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_active_version_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "unpin_reason")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "unpinned_by_user_id")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "unpinned_at")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "pin_reason")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "pinned_by_user_id")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "pinned_at")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "allow_explicit_version_override")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "version_selection_mode")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "pinned_version_id")
    op.drop_column("ai_system_governance_diagnostic_export_diff_gating_compare_presets", "active_version_id")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_ver_org_preset_num",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_ver_org_status",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_ver_org_preset",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
    )
    op.drop_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_versions_organization_id",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions",
    )
    op.drop_table("ai_system_governance_diagnostic_export_diff_gating_compare_preset_versions")
