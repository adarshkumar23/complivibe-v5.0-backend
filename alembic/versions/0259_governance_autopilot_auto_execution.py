"""governance autopilot auto execution and reversals

Revision ID: 0259_governance_autopilot_auto_execution
Revises: 0258_shared_link_password_lockout
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0259_governance_autopilot_auto_execution"
down_revision: str | None = "0258_shared_link_password_lockout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_governance_settings",
        sa.Column("autopilot_auto_execute_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "organization_governance_settings",
        sa.Column(
            "autopilot_auto_execute_confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.95"),
        ),
    )
    op.add_column(
        "organization_governance_settings",
        sa.Column(
            "autopilot_auto_execute_reversal_window_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )

    op.create_table(
        "governance_autopilot_executions",
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_key", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("risk_tier", sa.String(length=16), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("target_entity_type", sa.String(length=64), nullable=True),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_status", sa.String(length=32), nullable=False, server_default=sa.text("'executed'")),
        sa.Column("before_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("after_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("reversal_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("reversal_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reversed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_executions_org_status",
        "governance_autopilot_executions",
        ["organization_id", "execution_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_executions_org_intent",
        "governance_autopilot_executions",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_executions_org_created",
        "governance_autopilot_executions",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_executions_org_reversed",
        "governance_autopilot_executions",
        ["organization_id", "reversed_at"],
        unique=False,
    )

    op.alter_column("organization_governance_settings", "autopilot_auto_execute_enabled", server_default=None)
    op.alter_column(
        "organization_governance_settings",
        "autopilot_auto_execute_confidence_threshold",
        server_default=None,
    )
    op.alter_column(
        "organization_governance_settings",
        "autopilot_auto_execute_reversal_window_hours",
        server_default=None,
    )
    op.alter_column("governance_autopilot_executions", "confidence_score", server_default=None)
    op.alter_column("governance_autopilot_executions", "execution_status", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_executions_org_reversed",
        table_name="governance_autopilot_executions",
    )
    op.drop_index(
        "ix_governance_autopilot_executions_org_created",
        table_name="governance_autopilot_executions",
    )
    op.drop_index(
        "ix_governance_autopilot_executions_org_intent",
        table_name="governance_autopilot_executions",
    )
    op.drop_index(
        "ix_governance_autopilot_executions_org_status",
        table_name="governance_autopilot_executions",
    )
    op.drop_table("governance_autopilot_executions")

    op.drop_column("organization_governance_settings", "autopilot_auto_execute_reversal_window_hours")
    op.drop_column("organization_governance_settings", "autopilot_auto_execute_confidence_threshold")
    op.drop_column("organization_governance_settings", "autopilot_auto_execute_enabled")
