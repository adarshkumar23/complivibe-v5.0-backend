"""policy diff gating profiles and reports

Revision ID: 0050_policy_diff_gating_profiles
Revises: 0049_simulation_diff_reason_codes
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0050_policy_diff_gating_profiles"
down_revision: str | None = "0049_simulation_diff_reason_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_policy_diff_gating_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("default_severity", sa.String(length=16), nullable=False),
        sa.Column("review_required_threshold", sa.String(length=16), nullable=False),
        sa.Column("reason_code_rules_json", sa.JSON(), nullable=False),
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
        "ix_ai_system_governance_policy_diff_gating_profiles_organization_id",
        "ai_system_governance_policy_diff_gating_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_profiles_org_status",
        "ai_system_governance_policy_diff_gating_profiles",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_profiles_org_created",
        "ai_system_governance_policy_diff_gating_profiles",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_policy_diff_gating_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("diff_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gating_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("max_severity", sa.String(length=16), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("reason_code_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["diff_report_id"],
            ["ai_system_governance_policy_resolution_simulation_diff_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gating_profile_id"],
            ["ai_system_governance_policy_diff_gating_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_policy_diff_gating_reports_organization_id",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_status",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_created",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_diff",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id", "diff_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_profile",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id", "gating_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_review_req",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id", "review_required"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_max_severity",
        "ai_system_governance_policy_diff_gating_reports",
        ["organization_id", "max_severity"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_max_severity",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_review_req",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_profile",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_diff",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_created",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_reports_org_status",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_index(
        "ix_ai_system_governance_policy_diff_gating_reports_organization_id",
        table_name="ai_system_governance_policy_diff_gating_reports",
    )
    op.drop_table("ai_system_governance_policy_diff_gating_reports")

    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_profiles_org_created",
        table_name="ai_system_governance_policy_diff_gating_profiles",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_profiles_org_status",
        table_name="ai_system_governance_policy_diff_gating_profiles",
    )
    op.drop_index(
        "ix_ai_system_governance_policy_diff_gating_profiles_organization_id",
        table_name="ai_system_governance_policy_diff_gating_profiles",
    )
    op.drop_table("ai_system_governance_policy_diff_gating_profiles")
