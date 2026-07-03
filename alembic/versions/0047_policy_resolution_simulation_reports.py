"""policy resolution simulation reports

Revision ID: 0047_policy_resolution_simulation_reports
Revises: 0046_guardrail_policy_assignments
Create Date: 2026-06-20 01:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0047_policy_resolution_simulation_reports"
down_revision: str | None = "0046_guardrail_policy_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_policy_resolution_simulation_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_contexts_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("context_count", sa.Integer(), nullable=False),
        sa.Column("blocked_contexts_count", sa.Integer(), nullable=False),
        sa.Column("warning_contexts_count", sa.Integer(), nullable=False),
        sa.Column("no_policy_contexts_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pol_resolution_simulation_rpts_org_i_2eda254b",
        "ai_system_governance_policy_resolution_simulation_reports",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_res_sim_reports_org_status",
        "ai_system_governance_policy_resolution_simulation_reports",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_policy_res_sim_reports_org_created",
        "ai_system_governance_policy_resolution_simulation_reports",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_res_sim_reports_org_created",
        table_name="ai_system_governance_policy_resolution_simulation_reports",
    )
    op.drop_index(
        "ix_ai_sys_gov_policy_res_sim_reports_org_status",
        table_name="ai_system_governance_policy_resolution_simulation_reports",
    )
    op.drop_index(
        "ix_ai_system_gov_pol_resolution_simulation_rpts_org_i_2eda254b",
        table_name="ai_system_governance_policy_resolution_simulation_reports",
    )
    op.drop_table("ai_system_governance_policy_resolution_simulation_reports")
