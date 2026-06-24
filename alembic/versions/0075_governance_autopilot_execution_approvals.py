"""governance autopilot execution approvals envelope

Revision ID: 0075_governance_autopilot_execution_approvals
Revises: 0074_governance_autopilot_execution_intents
Create Date: 2026-06-21 00:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0075_governance_autopilot_execution_approvals"
down_revision: str | None = "0074_governance_autopilot_execution_intents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_execution_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approval_policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("approval_requirements_json", sa.JSON(), nullable=False),
        sa.Column("readiness_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_execution_approvals_organization_id",
        "governance_autopilot_execution_approvals",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approvals_org_status",
        "governance_autopilot_execution_approvals",
        ["organization_id", "approval_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approvals_org_intent",
        "governance_autopilot_execution_approvals",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approvals_org_requested",
        "governance_autopilot_execution_approvals",
        ["organization_id", "requested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_execution_approvals_org_requested",
        table_name="governance_autopilot_execution_approvals",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approvals_org_intent",
        table_name="governance_autopilot_execution_approvals",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approvals_org_status",
        table_name="governance_autopilot_execution_approvals",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approvals_organization_id",
        table_name="governance_autopilot_execution_approvals",
    )
    op.drop_table("governance_autopilot_execution_approvals")
