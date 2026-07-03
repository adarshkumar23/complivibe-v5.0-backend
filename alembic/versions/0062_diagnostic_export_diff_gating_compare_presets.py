"""diagnostic export diff gating compare presets and reports

Revision ID: 0062_diagnostic_export_diff_gating_compare_presets
Revises: 0061_diagnostic_export_diff_gating_compare_reports
Create Date: 2026-06-20 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0062_diagnostic_export_diff_gating_compare_presets"
down_revision: str | None = "0061_diagnostic_export_diff_gating_compare_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("watched_reason_codes_json", sa.JSON(), nullable=True),
        sa.Column("ignored_reason_codes_json", sa.JSON(), nullable=True),
        sa.Column("interpretation_rules_json", sa.JSON(), nullable=False),
        sa.Column("default_interpretation_band", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_presets_a33c3c29",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_status",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_created",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_band",
        "ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
        ["organization_id", "default_interpretation_band"],
        unique=False,
    )

    op.create_table(
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compare_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("interpretation_band", sa.String(length=32), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("matched_rules_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["compare_report_id"],
            ["ai_system_gov_diag_export_diff_gating_cmp_rpts_884d7a31.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_27131653",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_a53f6679",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_b246ded0",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_dc134d31",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "compare_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_d64984da",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_band",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "interpretation_band"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_8c01536c",
        "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
        ["organization_id", "review_required"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_8c01536c",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_band",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_d64984da",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_dc134d31",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_b246ded0",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_a53f6679",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_27131653",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df",
    )
    op.drop_table("ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_band",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_created",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_status",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
    )
    op.drop_index(
        "ix_ai_system_gov_diag_export_diff_gating_cmp_presets_a33c3c29",
        table_name="ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a",
    )
    op.drop_table("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a")
