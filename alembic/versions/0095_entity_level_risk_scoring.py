"""entity level risk scoring

Revision ID: 0095_entity_level_risk_scoring
Revises: 0094_factor_based_risk_decomposition
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0095_entity_level_risk_scoring"
down_revision: str | None = "0094_factor_based_risk_decomposition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_label", sa.String(length=255), nullable=False),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("score_band", sa.String(length=20), nullable=False),
        sa.Column("risk_count", sa.Integer(), nullable=False),
        sa.Column("score_method", sa.String(length=30), server_default=sa.text("'equal_weight'"), nullable=False),
        sa.Column("component_risks_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computation_notes", sa.Text(), nullable=True),
        sa.Column("computed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('vendor', 'asset', 'business_unit', 'framework')",
            name="ck_entity_risk_scores_entity_type",
        ),
        sa.CheckConstraint(
            "score_band IN ('critical', 'high', 'medium', 'low', 'none')",
            name="ck_entity_risk_scores_score_band",
        ),
        sa.CheckConstraint(
            "score_method IN ('equal_weight', 'max_score', 'weighted_avg')",
            name="ck_entity_risk_scores_score_method",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["computed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_entity_risk_scores_org_type_entity",
        "entity_risk_scores",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_risk_scores_org_type_computed",
        "entity_risk_scores",
        ["organization_id", "entity_type", "computed_at"],
        unique=False,
    )
    op.create_index(
        "ix_entity_risk_scores_org_band",
        "entity_risk_scores",
        ["organization_id", "score_band"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entity_risk_scores_org_band", table_name="entity_risk_scores")
    op.drop_index("ix_entity_risk_scores_org_type_computed", table_name="entity_risk_scores")
    op.drop_index("ix_entity_risk_scores_org_type_entity", table_name="entity_risk_scores")
    op.drop_table("entity_risk_scores")
