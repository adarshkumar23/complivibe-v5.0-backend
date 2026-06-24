"""governance autopilot approval policies and quorum votes

Revision ID: 0076_governance_autopilot_approval_policies_and_votes
Revises: 0075_governance_autopilot_execution_approvals
Create Date: 2026-06-21 02:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0076_governance_autopilot_approval_policies_and_votes"
down_revision: str | None = "0075_governance_autopilot_execution_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_approval_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("minimum_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rejection_threshold", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("require_distinct_approvers", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("block_requester_self_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("require_quorum_for_priority_bands_json", sa.JSON(), nullable=True),
        sa.Column("require_quorum_for_source_types_json", sa.JSON(), nullable=True),
        sa.Column("policy_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_approval_policies_organization_id",
        "governance_autopilot_approval_policies",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_approval_policies_org_status",
        "governance_autopilot_approval_policies",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_approval_policies_org_default",
        "governance_autopilot_approval_policies",
        ["organization_id", "is_default"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_approval_policies_org_created",
        "governance_autopilot_approval_policies",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "governance_autopilot_execution_approval_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vote_status", sa.String(length=32), nullable=False),
        sa.Column("voter_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vote_reason", sa.Text(), nullable=True),
        sa.Column("vote_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["governance_autopilot_execution_approvals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["governance_autopilot_execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voter_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "approval_id",
            "voter_user_id",
            name="uq_governance_autopilot_execution_approval_votes_org_approval_voter",
        ),
    )
    op.create_index(
        "ix_governance_autopilot_execution_approval_votes_organization_id",
        "governance_autopilot_execution_approval_votes",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approval_votes_org_approval",
        "governance_autopilot_execution_approval_votes",
        ["organization_id", "approval_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approval_votes_org_intent",
        "governance_autopilot_execution_approval_votes",
        ["organization_id", "execution_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approval_votes_org_status",
        "governance_autopilot_execution_approval_votes",
        ["organization_id", "vote_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_execution_approval_votes_org_voter",
        "governance_autopilot_execution_approval_votes",
        ["organization_id", "voter_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_autopilot_execution_approval_votes_org_voter",
        table_name="governance_autopilot_execution_approval_votes",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approval_votes_org_status",
        table_name="governance_autopilot_execution_approval_votes",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approval_votes_org_intent",
        table_name="governance_autopilot_execution_approval_votes",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approval_votes_org_approval",
        table_name="governance_autopilot_execution_approval_votes",
    )
    op.drop_index(
        "ix_governance_autopilot_execution_approval_votes_organization_id",
        table_name="governance_autopilot_execution_approval_votes",
    )
    op.drop_table("governance_autopilot_execution_approval_votes")

    op.drop_index(
        "ix_governance_autopilot_approval_policies_org_created",
        table_name="governance_autopilot_approval_policies",
    )
    op.drop_index(
        "ix_governance_autopilot_approval_policies_org_default",
        table_name="governance_autopilot_approval_policies",
    )
    op.drop_index(
        "ix_governance_autopilot_approval_policies_org_status",
        table_name="governance_autopilot_approval_policies",
    )
    op.drop_index(
        "ix_governance_autopilot_approval_policies_organization_id",
        table_name="governance_autopilot_approval_policies",
    )
    op.drop_table("governance_autopilot_approval_policies")
