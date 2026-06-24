"""governance recommendation snapshots and diffable history foundation

Revision ID: 0070_governance_recommendation_snapshots
Revises: 0069_ai_risk_classification_review_signals
Create Date: 2026-06-20 23:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0070_governance_recommendation_snapshots"
down_revision: str | None = "0069_ai_risk_classification_review_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_recommendation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="candidate_actions"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendation_payload_json", sa.JSON(), nullable=False),
        sa.Column("source_signal_ids_json", sa.JSON(), nullable=False),
        sa.Column("source_candidate_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("previous_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("diff_from_previous_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["governance_recommendation_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_governance_recommendation_snapshots_organization_id",
        "governance_recommendation_snapshots",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_recommendation_snapshots_org_scope",
        "governance_recommendation_snapshots",
        ["organization_id", "scope_type", "scope_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_recommendation_snapshots_org_created",
        "governance_recommendation_snapshots",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_governance_recommendation_snapshots_org_source",
        "governance_recommendation_snapshots",
        ["organization_id", "source_type"],
        unique=False,
    )
    op.create_index(
        "ix_governance_recommendation_snapshots_org_version",
        "governance_recommendation_snapshots",
        ["organization_id", "scope_type", "scope_id", "snapshot_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_governance_recommendation_snapshots_org_version", table_name="governance_recommendation_snapshots")
    op.drop_index("ix_governance_recommendation_snapshots_org_source", table_name="governance_recommendation_snapshots")
    op.drop_index("ix_governance_recommendation_snapshots_org_created", table_name="governance_recommendation_snapshots")
    op.drop_index("ix_governance_recommendation_snapshots_org_scope", table_name="governance_recommendation_snapshots")
    op.drop_index("ix_governance_recommendation_snapshots_organization_id", table_name="governance_recommendation_snapshots")
    op.drop_table("governance_recommendation_snapshots")
