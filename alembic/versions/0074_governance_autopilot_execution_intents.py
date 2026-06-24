"""governance autopilot execution planning intents

Revision ID: 0074_governance_autopilot_execution_intents
Revises: 0073_governance_autopilot_policies
Create Date: 2026-06-20 23:59:59.100000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0074_governance_autopilot_execution_intents"
down_revision: str | None = "0073_governance_autopilot_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_execution_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("intent_status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("plan_payload_json", sa.JSON(), nullable=False),
        sa.Column("capability_decisions_json", sa.JSON(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("blocked_reasons_json", sa.JSON(), nullable=True),
        sa.Column("source_entities_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("intent_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["governance_autopilot_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_execution_intents_organization_id",
        "governance_autopilot_execution_intents",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_intents_org_status",
        "governance_autopilot_execution_intents",
        ["organization_id", "intent_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_intents_org_source",
        "governance_autopilot_execution_intents",
        ["organization_id", "source_type", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_intents_org_policy",
        "governance_autopilot_execution_intents",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_intents_org_created",
        "governance_autopilot_execution_intents",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_execution_intents_org_created",
        table_name="governance_autopilot_execution_intents",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_intents_org_policy",
        table_name="governance_autopilot_execution_intents",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_intents_org_source",
        table_name="governance_autopilot_execution_intents",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_intents_org_status",
        table_name="governance_autopilot_execution_intents",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_intents_organization_id",
        table_name="governance_autopilot_execution_intents",
    )
    op.drop_table("governance_autopilot_execution_intents")
