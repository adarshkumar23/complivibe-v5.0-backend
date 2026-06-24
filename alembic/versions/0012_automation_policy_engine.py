"""automation policy engine foundation

Revision ID: 0012_automation_policy_engine
Revises: 0011_task_orchestration
Create Date: 2026-06-18 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_automation_policy_engine"
down_revision: Union[str, Sequence[str], None] = "0011_task_orchestration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=False, server_default="manual_scan"),
        sa.Column("condition_type", sa.String(length=64), nullable=False),
        sa.Column("condition_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_rules_org_status", "automation_rules", ["organization_id", "status"], unique=False)
    op.create_index("ix_automation_rules_org_trigger", "automation_rules", ["organization_id", "trigger_type"], unique=False)

    op.create_table(
        "automation_rule_executions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_exec_org_rule", "automation_rule_executions", ["organization_id", "rule_id"], unique=False)
    op.create_index("ix_automation_exec_org_status", "automation_rule_executions", ["organization_id", "status"], unique=False)

    op.create_table(
        "automation_action_logs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("created_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_email_outbox_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skipped_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["automation_rule_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_action_org_rule", "automation_action_logs", ["organization_id", "rule_id"], unique=False)
    op.create_index("ix_automation_action_org_execution", "automation_action_logs", ["organization_id", "execution_id"], unique=False)
    op.create_index("ix_automation_action_org_idempotency", "automation_action_logs", ["organization_id", "idempotency_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_automation_action_org_idempotency", table_name="automation_action_logs")
    op.drop_index("ix_automation_action_org_execution", table_name="automation_action_logs")
    op.drop_index("ix_automation_action_org_rule", table_name="automation_action_logs")
    op.drop_table("automation_action_logs")

    op.drop_index("ix_automation_exec_org_status", table_name="automation_rule_executions")
    op.drop_index("ix_automation_exec_org_rule", table_name="automation_rule_executions")
    op.drop_table("automation_rule_executions")

    op.drop_index("ix_automation_rules_org_trigger", table_name="automation_rules")
    op.drop_index("ix_automation_rules_org_status", table_name="automation_rules")
    op.drop_table("automation_rules")
