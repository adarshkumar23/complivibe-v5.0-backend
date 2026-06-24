"""vendor risk scoring and control linkage

Revision ID: 0087_vendor_risk_scoring_and_control_linkage
Revises: 0086_vendor_assessment_workflow
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0087_vendor_risk_scoring_and_control_linkage"
down_revision: str | None = "0086_vendor_assessment_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("likelihood", sa.String(length=16), nullable=False),
        sa.Column("impact", sa.String(length=16), nullable=False),
        sa.Column("inherent_risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("score_explanation_json", sa.JSON(), nullable=False),
        sa.Column("scored_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["vendor_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scored_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_risk_scores_organization_id", "vendor_risk_scores", ["organization_id"], unique=False)
    op.create_index("ix_vendor_risk_scores_org_vendor", "vendor_risk_scores", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_risk_scores_org_assessment", "vendor_risk_scores", ["organization_id", "assessment_id"], unique=False)
    op.create_index("ix_vendor_risk_scores_org_level", "vendor_risk_scores", ["organization_id", "risk_level"], unique=False)
    op.create_index("ix_vendor_risk_scores_org_created", "vendor_risk_scores", ["organization_id", "created_at"], unique=False)

    op.create_table(
        "vendor_control_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlink_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unlinked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_control_links_organization_id", "vendor_control_links", ["organization_id"], unique=False)
    op.create_index("ix_vendor_control_links_org_vendor", "vendor_control_links", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_control_links_org_control", "vendor_control_links", ["organization_id", "control_id"], unique=False)
    op.create_index("ix_vendor_control_links_org_status", "vendor_control_links", ["organization_id", "status"], unique=False)
    op.create_index("ix_vendor_control_links_org_created", "vendor_control_links", ["organization_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendor_control_links_org_created", table_name="vendor_control_links")
    op.drop_index("ix_vendor_control_links_org_status", table_name="vendor_control_links")
    op.drop_index("ix_vendor_control_links_org_control", table_name="vendor_control_links")
    op.drop_index("ix_vendor_control_links_org_vendor", table_name="vendor_control_links")
    op.drop_index("ix_vendor_control_links_organization_id", table_name="vendor_control_links")
    op.drop_table("vendor_control_links")

    op.drop_index("ix_vendor_risk_scores_org_created", table_name="vendor_risk_scores")
    op.drop_index("ix_vendor_risk_scores_org_level", table_name="vendor_risk_scores")
    op.drop_index("ix_vendor_risk_scores_org_assessment", table_name="vendor_risk_scores")
    op.drop_index("ix_vendor_risk_scores_org_vendor", table_name="vendor_risk_scores")
    op.drop_index("ix_vendor_risk_scores_organization_id", table_name="vendor_risk_scores")
    op.drop_table("vendor_risk_scores")
