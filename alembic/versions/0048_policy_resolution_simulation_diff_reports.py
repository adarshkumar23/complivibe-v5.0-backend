"""policy resolution simulation diff reports

Revision ID: 0048_policy_resolution_simulation_diff_reports
Revises: 0047_policy_resolution_simulation_reports
Create Date: 2026-06-20 02:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0048_policy_resolution_simulation_diff_reports"
down_revision: str | None = "0047_policy_resolution_simulation_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compare_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("context_match_strategy", sa.String(length=64), nullable=False),
        sa.Column("added_contexts_count", sa.Integer(), nullable=False),
        sa.Column("removed_contexts_count", sa.Integer(), nullable=False),
        sa.Column("changed_contexts_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_contexts_count", sa.Integer(), nullable=False),
        sa.Column("blocked_delta", sa.Integer(), nullable=False),
        sa.Column("warning_delta", sa.Integer(), nullable=False),
        sa.Column("no_policy_delta", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["base_report_id"],
            ["ai_system_governance_policy_resolution_simulation_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["compare_report_id"],
            ["ai_system_governance_policy_resolution_simulation_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pol_resolution_simulation_diff_rpts_0f711ee6",
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_status",
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_created",
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_base",
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        ["organization_id", "base_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_compare",
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        ["organization_id", "compare_report_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_compare",
        table_name="ai_system_governance_policy_resolution_simulation_diff_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_base",
        table_name="ai_system_governance_policy_resolution_simulation_diff_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_created",
        table_name="ai_system_governance_policy_resolution_simulation_diff_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_res_sim_diff_org_status",
        table_name="ai_system_governance_policy_resolution_simulation_diff_reports",
    )
    op.drop_index(
        "ix_ai_system_gov_pol_resolution_simulation_diff_rpts_0f711ee6",
        table_name="ai_system_governance_policy_resolution_simulation_diff_reports",
    )
    op.drop_table("ai_system_governance_policy_resolution_simulation_diff_reports")
