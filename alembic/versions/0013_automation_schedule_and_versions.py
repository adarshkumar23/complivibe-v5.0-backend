"""automation schedule metadata and rule versions

Revision ID: 0013_automation_schedule_and_versions
Revises: 0012_automation_policy_engine
Create Date: 2026-06-18 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_automation_schedule_and_versions"
down_revision: Union[str, Sequence[str], None] = "0012_automation_policy_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("automation_rules", sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("automation_rules", sa.Column("schedule_cadence", sa.String(length=32), nullable=True))
    op.add_column("automation_rules", sa.Column("schedule_timezone", sa.String(length=64), nullable=False, server_default="UTC"))
    op.add_column("automation_rules", sa.Column("schedule_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("schedule_end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("schedule_window_start", sa.String(length=5), nullable=True))
    op.add_column("automation_rules", sa.Column("schedule_window_end", sa.String(length=5), nullable=True))
    op.add_column("automation_rules", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("last_scheduled_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("last_dry_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("run_mode", sa.String(length=16), nullable=False, server_default="live"))
    op.add_column("automation_rules", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("automation_rules", sa.Column("version_notes", sa.Text(), nullable=True))

    op.create_table(
        "automation_rule_versions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("condition_type", sa.String(length=64), nullable=False),
        sa.Column("condition_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schedule_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_rule_versions_org_rule", "automation_rule_versions", ["organization_id", "rule_id"], unique=False)

    op.add_column("automation_rule_executions", sa.Column("trigger_source", sa.String(length=32), nullable=False, server_default="manual_rule_run"))
    op.add_column("automation_rule_executions", sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("automation_rule_executions", sa.Column("rule_version", sa.Integer(), nullable=True))
    op.add_column("automation_rule_executions", sa.Column("scheduled_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rule_executions", sa.Column("idempotency_scope", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("automation_rule_executions", "idempotency_scope")
    op.drop_column("automation_rule_executions", "scheduled_run_at")
    op.drop_column("automation_rule_executions", "rule_version")
    op.drop_column("automation_rule_executions", "dry_run")
    op.drop_column("automation_rule_executions", "trigger_source")

    op.drop_index("ix_automation_rule_versions_org_rule", table_name="automation_rule_versions")
    op.drop_table("automation_rule_versions")

    op.drop_column("automation_rules", "version_notes")
    op.drop_column("automation_rules", "version")
    op.drop_column("automation_rules", "run_mode")
    op.drop_column("automation_rules", "last_dry_run_at")
    op.drop_column("automation_rules", "last_scheduled_run_at")
    op.drop_column("automation_rules", "next_run_at")
    op.drop_column("automation_rules", "schedule_window_end")
    op.drop_column("automation_rules", "schedule_window_start")
    op.drop_column("automation_rules", "schedule_end_at")
    op.drop_column("automation_rules", "schedule_start_at")
    op.drop_column("automation_rules", "schedule_timezone")
    op.drop_column("automation_rules", "schedule_cadence")
    op.drop_column("automation_rules", "schedule_enabled")
