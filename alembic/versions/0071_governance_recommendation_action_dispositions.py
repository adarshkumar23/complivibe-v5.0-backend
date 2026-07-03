"""governance recommendation action disposition controls

Revision ID: 0071_governance_recommendation_action_dispositions
Revises: 0070_governance_recommendation_snapshots
Create Date: 2026-06-20 23:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0071_governance_recommendation_action_dispositions"
down_revision: str | None = "0070_governance_recommendation_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_recommendation_action_dispositions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("action_key", sa.String(length=128), nullable=False),
        sa.Column("target_entity_type", sa.String(length=64), nullable=True),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("disposition_status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("deferred_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recommendation_snapshot_id"],
            ["governance_recommendation_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["related_ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_risk_assessment_id"], ["ai_system_risk_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_gov_rec_action_disp_org_id_3a936372",
        "governance_recommendation_action_dispositions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ux_governance_reco_action_disp_org_snapshot_action",
        "governance_recommendation_action_dispositions",
        ["organization_id", "recommendation_snapshot_id", "action_identity_hash"],
        unique=True,
    )
    op.create_index(
        "ix_governance_reco_action_disp_org_status",
        "governance_recommendation_action_dispositions",
        ["organization_id", "disposition_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_reco_action_disp_org_snapshot",
        "governance_recommendation_action_dispositions",
        ["organization_id", "recommendation_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_reco_action_disp_org_action_key",
        "governance_recommendation_action_dispositions",
        ["organization_id", "action_key"],
        unique=False,
    )
    op.create_index(
        "ix_governance_reco_action_disp_org_ai",
        "governance_recommendation_action_dispositions",
        ["organization_id", "related_ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_reco_action_disp_org_assessment",
        "governance_recommendation_action_dispositions",
        ["organization_id", "related_risk_assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_reco_action_disp_org_updated",
        "governance_recommendation_action_dispositions",
        ["organization_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_governance_reco_action_disp_org_updated", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ix_governance_reco_action_disp_org_assessment", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ix_governance_reco_action_disp_org_ai", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ix_governance_reco_action_disp_org_action_key", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ix_governance_reco_action_disp_org_snapshot", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ix_governance_reco_action_disp_org_status", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ux_governance_reco_action_disp_org_snapshot_action", table_name="governance_recommendation_action_dispositions")
    op.drop_index("ix_gov_rec_action_disp_org_id_3a936372", table_name="governance_recommendation_action_dispositions")
    op.drop_table("governance_recommendation_action_dispositions")
