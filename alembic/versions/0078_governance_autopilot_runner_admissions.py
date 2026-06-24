"""governance autopilot runner admissions

Revision ID: 0078_governance_autopilot_runner_admissions
Revises: 0077_governance_autopilot_runner_simulations
Create Date: 2026-06-21 07:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0078_governance_autopilot_runner_admissions"
down_revision: str | None = "0077_governance_autopilot_runner_simulations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_runner_admissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_simulation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("admission_status", sa.String(length=32), nullable=False),
        sa.Column("readiness_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("consistency_checks_json", sa.JSON(), nullable=False),
        sa.Column("handoff_payload_json", sa.JSON(), nullable=False),
        sa.Column("handoff_token_hash", sa.String(length=64), nullable=True),
        sa.Column("handoff_token_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_simulation_id"], ["governance_autopilot_runner_simulations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["governance_autopilot_execution_approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["admitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_organization_id",
        "governance_autopilot_runner_admissions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_org_status",
        "governance_autopilot_runner_admissions",
        ["organization_id", "admission_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_org_simulation",
        "governance_autopilot_runner_admissions",
        ["organization_id", "runner_simulation_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_org_intent",
        "governance_autopilot_runner_admissions",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_org_approval",
        "governance_autopilot_runner_admissions",
        ["organization_id", "approval_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_org_idempotency",
        "governance_autopilot_runner_admissions",
        ["organization_id", "idempotency_key"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_admissions_org_created",
        "governance_autopilot_runner_admissions",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_org_created",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_org_idempotency",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_org_approval",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_org_intent",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_org_simulation",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_org_status",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_admissions_organization_id",
        table_name="governance_autopilot_runner_admissions",
    )
    op.drop_table("governance_autopilot_runner_admissions")
