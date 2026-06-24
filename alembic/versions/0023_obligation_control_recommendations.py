"""obligation control recommendation layer

Revision ID: 0023_obligation_control_recommendations
Revises: 0022_applicability_answers_and_evaluation
Create Date: 2026-06-19 10:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023_obligation_control_recommendations"
down_revision: Union[str, Sequence[str], None] = "0022_applicability_answers_and_evaluation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "obligation_control_recommendations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_type", sa.String(length=48), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("recommended_control_title", sa.String(length=255), nullable=True),
        sa.Column("recommended_control_description", sa.Text(), nullable=True),
        sa.Column("existing_control_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_control_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence_level", sa.String(length=32), nullable=False, server_default="deterministic_partial"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suggestion_id"], ["obligation_control_suggestions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["existing_control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dismissed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obl_ctrl_reco_org_framework", "obligation_control_recommendations", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_obl_ctrl_reco_org_obligation", "obligation_control_recommendations", ["organization_id", "obligation_id"], unique=False)
    op.create_index("ix_obl_ctrl_reco_org_status", "obligation_control_recommendations", ["organization_id", "status"], unique=False)
    op.create_index("ix_obl_ctrl_reco_org_priority", "obligation_control_recommendations", ["organization_id", "priority"], unique=False)
    op.create_index("ix_obl_ctrl_reco_org_type", "obligation_control_recommendations", ["organization_id", "recommendation_type"], unique=False)
    op.create_index("ix_obl_ctrl_reco_org_source", "obligation_control_recommendations", ["organization_id", "source"], unique=False)
    op.create_index("ix_obl_ctrl_reco_org_generated", "obligation_control_recommendations", ["organization_id", "generated_at"], unique=False)

    op.create_table(
        "recommendation_generation_runs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_obligations_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendations_created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendations_skipped_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendations_would_create_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reco_run_org_framework", "recommendation_generation_runs", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_reco_run_org_status", "recommendation_generation_runs", ["organization_id", "status"], unique=False)
    op.create_index("ix_reco_run_org_created", "recommendation_generation_runs", ["organization_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reco_run_org_created", table_name="recommendation_generation_runs")
    op.drop_index("ix_reco_run_org_status", table_name="recommendation_generation_runs")
    op.drop_index("ix_reco_run_org_framework", table_name="recommendation_generation_runs")
    op.drop_table("recommendation_generation_runs")

    op.drop_index("ix_obl_ctrl_reco_org_generated", table_name="obligation_control_recommendations")
    op.drop_index("ix_obl_ctrl_reco_org_source", table_name="obligation_control_recommendations")
    op.drop_index("ix_obl_ctrl_reco_org_type", table_name="obligation_control_recommendations")
    op.drop_index("ix_obl_ctrl_reco_org_priority", table_name="obligation_control_recommendations")
    op.drop_index("ix_obl_ctrl_reco_org_status", table_name="obligation_control_recommendations")
    op.drop_index("ix_obl_ctrl_reco_org_obligation", table_name="obligation_control_recommendations")
    op.drop_index("ix_obl_ctrl_reco_org_framework", table_name="obligation_control_recommendations")
    op.drop_table("obligation_control_recommendations")
