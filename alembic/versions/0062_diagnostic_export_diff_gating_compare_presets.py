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
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
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
        "ix_ai_system_governance_diag_export_diff_gating_cmp_presets_organization_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_status",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_created",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_band",
        "ai_system_governance_diagnostic_export_diff_gating_compare_presets",
        ["organization_id", "default_interpretation_band"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
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
            ["ai_system_governance_diagnostic_export_diff_gating_compare_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["ai_system_governance_diagnostic_export_diff_gating_compare_presets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_reports_organization_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_status",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_created",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_compare",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "compare_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_preset",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_band",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "interpretation_band"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_review_req",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
        ["organization_id", "review_required"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_review_req",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_band",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_preset",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_compare",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_created",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_status",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_reports_organization_id",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports",
    )
    op.drop_table("ai_system_governance_diagnostic_export_diff_gating_compare_preset_reports")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_band",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_presets",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_created",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_presets",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_org_status",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_presets",
    )
    op.drop_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_presets_organization_id",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_presets",
    )
    op.drop_table("ai_system_governance_diagnostic_export_diff_gating_compare_presets")
