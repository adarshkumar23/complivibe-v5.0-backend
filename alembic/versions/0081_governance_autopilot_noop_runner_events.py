"""governance autopilot noop runner events

Revision ID: 0081_governance_autopilot_noop_runner_events
Revises: 0080_governance_autopilot_runner_handshakes
Create Date: 2026-06-21 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0081_governance_autopilot_noop_runner_events"
down_revision: str | None = "0080_governance_autopilot_runner_handshakes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_noop_runner_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_handshake_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_admission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_simulation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_status", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("noop_only", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("execution_allowed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("event_payload_json", sa.JSON(), nullable=False),
        sa.Column("noop_result_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("event_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_handshake_id"], ["governance_autopilot_runner_handshakes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_session_id"], ["governance_autopilot_runner_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_admission_id"], ["governance_autopilot_runner_admissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_simulation_id"], ["governance_autopilot_runner_simulations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_organization_id",
        "governance_autopilot_noop_runner_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_status",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "event_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_type",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "event_type"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_handshake",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "runner_handshake_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_session",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "runner_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_admission",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "runner_admission_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_simulation",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "runner_simulation_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_intent",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_idempotency",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "idempotency_key"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_noop_runner_events_org_created",
        "governance_autopilot_noop_runner_events",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_created",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_idempotency",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_intent",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_simulation",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_admission",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_session",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_handshake",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_type",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_org_status",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_index(
        "ix_governance_autopilot_noop_runner_events_organization_id",
        table_name="governance_autopilot_noop_runner_events",
    )
    op.drop_table("governance_autopilot_noop_runner_events")
