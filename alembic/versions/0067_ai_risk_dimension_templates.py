"""ai risk dimension templates

Revision ID: 0067_ai_risk_dimension_templates
Revises: 0066_ai_risk_scoring_profiles
Create Date: 2026-06-20 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0067_ai_risk_dimension_templates"
down_revision: str | None = "0066_ai_risk_scoring_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_risk_dimension_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dimension_weights_json", sa.JSON(), nullable=False),
        sa.Column("dimension_thresholds_json", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_risk_dimension_templates_organization_id",
        "ai_system_risk_dimension_templates",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_dimension_templates_org_status",
        "ai_system_risk_dimension_templates",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_dimension_templates_org_default",
        "ai_system_risk_dimension_templates",
        ["organization_id", "is_default"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_dimension_templates_org_archived",
        "ai_system_risk_dimension_templates",
        ["organization_id", "archived_at"],
        unique=False,
    )

    op.add_column("ai_system_risk_assessments", sa.Column("dimension_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("dimension_template_snapshot_json", sa.JSON(), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("dimension_inputs_json", sa.JSON(), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("dimension_score_json", sa.JSON(), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("dimension_weighted_score", sa.Float(), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("calculated_dimension_risk_level", sa.String(length=32), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("residual_likelihood", sa.String(length=32), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("residual_impact", sa.String(length=32), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("calculated_residual_risk_level", sa.String(length=32), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("residual_score_explanation_json", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_ai_system_risk_assessments_dimension_template_id",
        "ai_system_risk_assessments",
        "ai_system_risk_dimension_templates",
        ["dimension_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_dimension_template",
        "ai_system_risk_assessments",
        ["organization_id", "dimension_template_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_calculated_dimension_risk_level",
        "ai_system_risk_assessments",
        ["organization_id", "calculated_dimension_risk_level"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_calculated_residual_risk_level",
        "ai_system_risk_assessments",
        ["organization_id", "calculated_residual_risk_level"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_system_risk_assessments_org_calculated_residual_risk_level",
        table_name="ai_system_risk_assessments",
    )
    op.drop_index(
        "ix_ai_system_risk_assessments_org_calculated_dimension_risk_level",
        table_name="ai_system_risk_assessments",
    )
    op.drop_index("ix_ai_system_risk_assessments_org_dimension_template", table_name="ai_system_risk_assessments")
    op.drop_constraint(
        "fk_ai_system_risk_assessments_dimension_template_id",
        "ai_system_risk_assessments",
        type_="foreignkey",
    )
    op.drop_column("ai_system_risk_assessments", "residual_score_explanation_json")
    op.drop_column("ai_system_risk_assessments", "calculated_residual_risk_level")
    op.drop_column("ai_system_risk_assessments", "residual_impact")
    op.drop_column("ai_system_risk_assessments", "residual_likelihood")
    op.drop_column("ai_system_risk_assessments", "calculated_dimension_risk_level")
    op.drop_column("ai_system_risk_assessments", "dimension_weighted_score")
    op.drop_column("ai_system_risk_assessments", "dimension_score_json")
    op.drop_column("ai_system_risk_assessments", "dimension_inputs_json")
    op.drop_column("ai_system_risk_assessments", "dimension_template_snapshot_json")
    op.drop_column("ai_system_risk_assessments", "dimension_template_id")

    op.drop_index("ix_ai_system_risk_dimension_templates_org_archived", table_name="ai_system_risk_dimension_templates")
    op.drop_index("ix_ai_system_risk_dimension_templates_org_default", table_name="ai_system_risk_dimension_templates")
    op.drop_index("ix_ai_system_risk_dimension_templates_org_status", table_name="ai_system_risk_dimension_templates")
    op.drop_index("ix_ai_system_risk_dimension_templates_organization_id", table_name="ai_system_risk_dimension_templates")
    op.drop_table("ai_system_risk_dimension_templates")
