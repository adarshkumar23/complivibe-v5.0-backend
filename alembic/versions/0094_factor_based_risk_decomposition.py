"""factor based risk decomposition

Revision ID: 0094_factor_based_risk_decomposition
Revises: 0093_risk_appetite_framework
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0094_factor_based_risk_decomposition"
down_revision: str | None = "0093_risk_appetite_framework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("risks", sa.Column("financial_impact", sa.SmallInteger(), nullable=True))
    op.add_column("risks", sa.Column("brand_impact", sa.SmallInteger(), nullable=True))
    op.add_column("risks", sa.Column("operational_impact", sa.SmallInteger(), nullable=True))
    op.add_column(
        "risks",
        sa.Column(
            "composite_score_method",
            sa.String(length=20),
            server_default=sa.text("'standard'"),
            nullable=False,
        ),
    )

    op.create_check_constraint("ck_risks_financial_impact_1_5", "risks", "financial_impact BETWEEN 1 AND 5")
    op.create_check_constraint("ck_risks_brand_impact_1_5", "risks", "brand_impact BETWEEN 1 AND 5")
    op.create_check_constraint("ck_risks_operational_impact_1_5", "risks", "operational_impact BETWEEN 1 AND 5")
    op.create_check_constraint(
        "ck_risks_composite_score_method",
        "risks",
        "composite_score_method IN ('standard', 'factor_based')",
    )

    op.create_table(
        "org_risk_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_weight", sa.Numeric(4, 3), server_default=sa.text("0.400"), nullable=False),
        sa.Column("brand_weight", sa.Numeric(4, 3), server_default=sa.text("0.300"), nullable=False),
        sa.Column("operational_weight", sa.Numeric(4, 3), server_default=sa.text("0.300"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("financial_weight >= 0.0 AND financial_weight <= 1.0", name="ck_org_risk_settings_financial_weight"),
        sa.CheckConstraint("brand_weight >= 0.0 AND brand_weight <= 1.0", name="ck_org_risk_settings_brand_weight"),
        sa.CheckConstraint(
            "operational_weight >= 0.0 AND operational_weight <= 1.0",
            name="ck_org_risk_settings_operational_weight",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_org_risk_settings_organization_id", "org_risk_settings", ["organization_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_org_risk_settings_organization_id", table_name="org_risk_settings")
    op.drop_table("org_risk_settings")

    op.drop_constraint("ck_risks_composite_score_method", "risks", type_="check")
    op.drop_constraint("ck_risks_operational_impact_1_5", "risks", type_="check")
    op.drop_constraint("ck_risks_brand_impact_1_5", "risks", type_="check")
    op.drop_constraint("ck_risks_financial_impact_1_5", "risks", type_="check")

    op.drop_column("risks", "composite_score_method")
    op.drop_column("risks", "operational_impact")
    op.drop_column("risks", "brand_impact")
    op.drop_column("risks", "financial_impact")
