"""ai system governance recurrence templates and plan runs

Revision ID: 0040_ai_system_governance_recurrence_templates
Revises: 0039_ai_system_governance_review_scheduling
Create Date: 2026-06-19 17:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0040_ai_system_governance_recurrence_templates"
down_revision: str | None = "0039_ai_system_governance_review_scheduling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_review_recurrence_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("cadence_type", sa.String(length=32), nullable=False),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column("default_reminder_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_checklist_json", sa.JSON(), nullable=True),
        sa.Column("default_description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["default_assigned_to_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["default_reminder_policy_id"],
            ["ai_system_governance_review_reminder_policies.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_review_recurrence_templates_organization_id",
        "ai_system_governance_review_recurrence_templates",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_recur_templates_org_status",
        "ai_system_governance_review_recurrence_templates",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_recur_templates_org_review_type",
        "ai_system_governance_review_recurrence_templates",
        ["organization_id", "review_type"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_review_plan_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("target_ai_system_ids_json", sa.JSON(), nullable=True),
        sa.Column("generated_reviews_count", sa.Integer(), nullable=False),
        sa.Column("skipped_reviews_count", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["ai_system_governance_review_recurrence_templates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_review_plan_runs_organization_id",
        "ai_system_governance_review_plan_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_plan_runs_org_status",
        "ai_system_governance_review_plan_runs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_plan_runs_org_template",
        "ai_system_governance_review_plan_runs",
        ["organization_id", "template_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_plan_runs_org_created",
        "ai_system_governance_review_plan_runs",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_sys_gov_review_plan_runs_org_created", table_name="ai_system_governance_review_plan_runs")
    op.drop_index("ix_ai_sys_gov_review_plan_runs_org_template", table_name="ai_system_governance_review_plan_runs")
    op.drop_index("ix_ai_sys_gov_review_plan_runs_org_status", table_name="ai_system_governance_review_plan_runs")
    op.drop_index("ix_ai_system_governance_review_plan_runs_organization_id", table_name="ai_system_governance_review_plan_runs")
    op.drop_table("ai_system_governance_review_plan_runs")

    op.drop_index(
        "ix_ai_sys_gov_review_recur_templates_org_review_type",
        table_name="ai_system_governance_review_recurrence_templates",
    )
    op.drop_index(
        "ix_ai_sys_gov_review_recur_templates_org_status",
        table_name="ai_system_governance_review_recurrence_templates",
    )
    op.drop_index(
        "ix_ai_system_governance_review_recurrence_templates_organization_id",
        table_name="ai_system_governance_review_recurrence_templates",
    )
    op.drop_table("ai_system_governance_review_recurrence_templates")
