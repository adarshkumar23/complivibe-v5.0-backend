"""control monitoring alert workflow

Revision ID: 0090_control_monitoring_alert_workflow
Revises: 0089_control_monitoring_rule_engine
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0090_control_monitoring_alert_workflow"
down_revision: str | None = "0089_control_monitoring_rule_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_monitoring_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("alert_context_json", sa.JSON(), nullable=True),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["control_monitoring_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["definition_id"], ["control_monitoring_definitions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dismissed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_monitoring_alerts_organization_id", "control_monitoring_alerts", ["organization_id"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_status", "control_monitoring_alerts", ["organization_id", "status"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_severity", "control_monitoring_alerts", ["organization_id", "severity"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_type", "control_monitoring_alerts", ["organization_id", "alert_type"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_assigned", "control_monitoring_alerts", ["organization_id", "assigned_to_user_id"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_rule", "control_monitoring_alerts", ["organization_id", "rule_id"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_definition", "control_monitoring_alerts", ["organization_id", "definition_id"], unique=False)
    op.create_index("ix_control_monitoring_alerts_org_control", "control_monitoring_alerts", ["organization_id", "control_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_control_monitoring_alerts_org_control", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_org_definition", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_org_rule", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_org_assigned", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_org_type", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_org_severity", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_org_status", table_name="control_monitoring_alerts")
    op.drop_index("ix_control_monitoring_alerts_organization_id", table_name="control_monitoring_alerts")
    op.drop_table("control_monitoring_alerts")
