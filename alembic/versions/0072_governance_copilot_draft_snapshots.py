"""governance copilot draft snapshots

Revision ID: 0072_governance_copilot_draft_snapshots
Revises: 0071_governance_recommendation_action_dispositions
Create Date: 2026-06-20 23:59:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0072_governance_copilot_draft_snapshots"
down_revision: str | None = "0071_governance_recommendation_action_dispositions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_copilot_draft_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_type", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_payload_json", sa.JSON(), nullable=False),
        sa.Column("source_entities_json", sa.JSON(), nullable=False),
        sa.Column("source_signal_ids_json", sa.JSON(), nullable=False),
        sa.Column("source_recommendation_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_action_identity_hashes_json", sa.JSON(), nullable=False),
        sa.Column("source_context_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("previous_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("diff_from_previous_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_recommendation_snapshot_id"], ["governance_recommendation_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["governance_copilot_draft_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_governance_copilot_draft_snapshots_organization_id",
        "governance_copilot_draft_snapshots",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_copilot_draft_snapshots_org_scope",
        "governance_copilot_draft_snapshots",
        ["organization_id", "draft_type", "scope_type", "scope_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_copilot_draft_snapshots_org_created",
        "governance_copilot_draft_snapshots",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_governance_copilot_draft_snapshots_org_version",
        "governance_copilot_draft_snapshots",
        ["organization_id", "draft_type", "scope_type", "scope_id", "snapshot_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_governance_copilot_draft_snapshots_org_version", table_name="governance_copilot_draft_snapshots")
    op.drop_index("ix_governance_copilot_draft_snapshots_org_created", table_name="governance_copilot_draft_snapshots")
    op.drop_index("ix_governance_copilot_draft_snapshots_org_scope", table_name="governance_copilot_draft_snapshots")
    op.drop_index("ix_governance_copilot_draft_snapshots_organization_id", table_name="governance_copilot_draft_snapshots")
    op.drop_table("governance_copilot_draft_snapshots")
