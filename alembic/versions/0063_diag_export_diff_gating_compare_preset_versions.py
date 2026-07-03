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
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
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
            ["ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_vers_22dd0353",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_808bfd21",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_c0d13057",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_3d2e08a6",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["organization_id", "preset_id", "version_number"],
        unique=False,
    )

    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("pinned_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column(
            "version_selection_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active_then_mutable'"),
        ),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column(
            "allow_explicit_version_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("pinned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("pin_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("unpinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("unpinned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("unpin_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_act_6912fb49",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pin_7e97644f",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["pinned_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pin_653ad67e",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        "users",
        ["pinned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_unp_572a2b2a",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        "users",
        ["unpinned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_org_act_f1f8507b",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        ["organization_id", "active_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_org_pin_274463a6",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        ["organization_id", "pinned_version_id"],
        unique=False,
    )

    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("preset_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("preset_version_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("preset_snapshot_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("version_resolution_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("pinned_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column(
            "explicit_version_override_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("version_override_reason", sa.String(length=2000), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_ver_833814e4",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["preset_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_pin_3e8a9e98",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
        ["pinned_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_08580bd2",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "preset_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_08580bd2",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_pin_3e8a9e98",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_ver_833814e4",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        type_="foreignkey",
    )
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "version_override_reason")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "explicit_version_override_used")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "pinned_version_id")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "version_resolution_source")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "preset_snapshot_json")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "preset_version_number")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df", "preset_version_id")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_org_pin_274463a6",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_org_act_f1f8507b",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_unp_572a2b2a",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pin_653ad67e",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_pin_7e97644f",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_diag_export_diff_gating_cmp_presets_act_6912fb49",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        type_="foreignkey",
    )
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "unpin_reason")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "unpinned_by_user_id")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "unpinned_at")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "pin_reason")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "pinned_by_user_id")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "pinned_at")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "allow_explicit_version_override")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "version_selection_mode")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "pinned_version_id")
    op.drop_column("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a", "active_version_id")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_3d2e08a6",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_c0d13057",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_808bfd21",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
    )
    op.drop_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_vers_22dd0353",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c",
    )
    op.drop_table("ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c")
