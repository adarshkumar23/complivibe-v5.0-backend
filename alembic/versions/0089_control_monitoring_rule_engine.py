"""control monitoring rule engine

Revision ID: 0089_control_monitoring_rule_engine
Revises: 0088_continuous_control_monitoring_foundation
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0089_control_monitoring_rule_engine"
down_revision: str | None = "0088_continuous_control_monitoring_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_monitoring_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("condition_json", sa.JSON(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("action_config_json", sa.JSON(), nullable=False),
        sa.Column("scope_definition_ids", sa.JSON(), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_monitoring_rules_organization_id", "control_monitoring_rules", ["organization_id"], unique=False)
    op.create_index("ix_control_monitoring_rules_org_status", "control_monitoring_rules", ["organization_id", "status"], unique=False)
    op.create_index("ix_control_monitoring_rules_org_type", "control_monitoring_rules", ["organization_id", "rule_type"], unique=False)
    op.create_index("ix_control_monitoring_rules_org_created", "control_monitoring_rules", ["organization_id", "created_at"], unique=False)

    op.create_table(
        "control_monitoring_rule_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("action_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("execution_summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["control_monitoring_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_monitoring_rule_executions_organization_id", "control_monitoring_rule_executions", ["organization_id"], unique=False)
    op.create_index("ix_control_monitoring_rule_executions_org_rule", "control_monitoring_rule_executions", ["organization_id", "rule_id"], unique=False)
    op.create_index("ix_control_monitoring_rule_executions_org_triggered", "control_monitoring_rule_executions", ["organization_id", "triggered_at"], unique=False)
    op.create_index("ix_control_monitoring_rule_executions_org_dry_run", "control_monitoring_rule_executions", ["organization_id", "dry_run"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_control_monitoring_rule_executions_org_dry_run", table_name="control_monitoring_rule_executions")
    op.drop_index("ix_control_monitoring_rule_executions_org_triggered", table_name="control_monitoring_rule_executions")
    op.drop_index("ix_control_monitoring_rule_executions_org_rule", table_name="control_monitoring_rule_executions")
    op.drop_index("ix_control_monitoring_rule_executions_organization_id", table_name="control_monitoring_rule_executions")
    op.drop_table("control_monitoring_rule_executions")

    op.drop_index("ix_control_monitoring_rules_org_created", table_name="control_monitoring_rules")
    op.drop_index("ix_control_monitoring_rules_org_type", table_name="control_monitoring_rules")
    op.drop_index("ix_control_monitoring_rules_org_status", table_name="control_monitoring_rules")
    op.drop_index("ix_control_monitoring_rules_organization_id", table_name="control_monitoring_rules")
    op.drop_table("control_monitoring_rules")
