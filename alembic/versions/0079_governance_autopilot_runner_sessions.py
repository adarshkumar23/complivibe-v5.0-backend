"""governance autopilot runner sessions

Revision ID: 0079_governance_autopilot_runner_sessions
Revises: 0078_governance_autopilot_runner_admissions
Create Date: 2026-06-21 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0079_governance_autopilot_runner_sessions"
down_revision: str | None = "0078_governance_autopilot_runner_admissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_runner_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_admission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_simulation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_status", sa.String(length=32), nullable=False),
        sa.Column("admission_token_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("session_token_hash", sa.String(length=64), nullable=True),
        sa.Column("session_token_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("lease_payload_json", sa.JSON(), nullable=False),
        sa.Column("binding_context_json", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("replay_window_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_admission_id"], ["governance_autopilot_runner_admissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_simulation_id"], ["governance_autopilot_runner_simulations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_organization_id",
        "governance_autopilot_runner_sessions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_org_status",
        "governance_autopilot_runner_sessions",
        ["organization_id", "session_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_org_admission",
        "governance_autopilot_runner_sessions",
        ["organization_id", "runner_admission_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_org_simulation",
        "governance_autopilot_runner_sessions",
        ["organization_id", "runner_simulation_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_org_intent",
        "governance_autopilot_runner_sessions",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_org_expires",
        "governance_autopilot_runner_sessions",
        ["organization_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_runner_sessions_org_created",
        "governance_autopilot_runner_sessions",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_org_created",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_org_expires",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_org_intent",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_org_simulation",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_org_admission",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_org_status",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_index(
        "ix_governance_autopilot_runner_sessions_organization_id",
        table_name="governance_autopilot_runner_sessions",
    )
    op.drop_table("governance_autopilot_runner_sessions")
