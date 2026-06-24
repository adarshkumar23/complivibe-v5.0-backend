"""governance autopilot runner simulations

Revision ID: 0077_governance_autopilot_runner_simulations
Revises: 0076_governance_autopilot_approval_policies_and_votes
Create Date: 2026-06-21 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0077_governance_autopilot_runner_simulations"
down_revision: str | None = "0076_governance_autopilot_approval_policies_and_votes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_runner_simulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("simulation_status", sa.String(length=32), nullable=False),
        sa.Column("handoff_payload_json", sa.JSON(), nullable=False),
        sa.Column("readiness_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("simulation_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["governance_autopilot_execution_approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_runner_simulations_organization_id",
        "governance_autopilot_runner_simulations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_simulations_org_status",
        "governance_autopilot_runner_simulations",
        ["organization_id", "simulation_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_simulations_org_intent",
        "governance_autopilot_runner_simulations",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_simulations_org_approval",
        "governance_autopilot_runner_simulations",
        ["organization_id", "approval_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_simulations_org_idempotency",
        "governance_autopilot_runner_simulations",
        ["organization_id", "idempotency_key"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_simulations_org_created",
        "governance_autopilot_runner_simulations",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_runner_simulations_org_created",
        table_name="governance_autopilot_runner_simulations",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_simulations_org_idempotency",
        table_name="governance_autopilot_runner_simulations",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_simulations_org_approval",
        table_name="governance_autopilot_runner_simulations",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_simulations_org_intent",
        table_name="governance_autopilot_runner_simulations",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_simulations_org_status",
        table_name="governance_autopilot_runner_simulations",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_simulations_organization_id",
        table_name="governance_autopilot_runner_simulations",
    )
    op.drop_table("governance_autopilot_runner_simulations")
