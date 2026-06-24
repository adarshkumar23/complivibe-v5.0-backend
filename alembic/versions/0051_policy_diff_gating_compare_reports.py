"""policy diff gating compare reports

Revision ID: 0051_policy_diff_gating_compare_reports
Revises: 0050_policy_diff_gating_profiles
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0051_policy_diff_gating_compare_reports"
down_revision: str | None = "0050_policy_diff_gating_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_policy_diff_gating_compare_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_gating_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compare_gating_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("base_max_severity", sa.String(length=16), nullable=False),
        sa.Column("compare_max_severity", sa.String(length=16), nullable=False),
        sa.Column("severity_direction", sa.String(length=16), nullable=False),
        sa.Column("review_required_changed", sa.Boolean(), nullable=False),
        sa.Column("base_review_required", sa.Boolean(), nullable=False),
        sa.Column("compare_review_required", sa.Boolean(), nullable=False),
        sa.Column("reason_code_changes_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["base_gating_report_id"],
            ["ai_system_governance_policy_diff_gating_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["compare_gating_report_id"],
            ["ai_system_governance_policy_diff_gating_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_policy_diff_gating_compare_reports_organization_id",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_status",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_created",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_base",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id", "base_gating_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_compare",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id", "compare_gating_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_sev_dir",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id", "severity_direction"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_rr_changed",
        "ai_system_governance_policy_diff_gating_compare_reports",
        ["organization_id", "review_required_changed"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_rr_changed",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_sev_dir",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_compare",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_base",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_created",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_org_status",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_index(
        "ix_ai_system_governance_policy_diff_gating_compare_reports_organization_id",
        table_name="ai_system_governance_policy_diff_gating_compare_reports",
    )
    op.drop_table("ai_system_governance_policy_diff_gating_compare_reports")
