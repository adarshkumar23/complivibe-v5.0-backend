"""compliance risk recommendations

Revision ID: 0183_compliance_risk_recommendations
Revises: 0182_mlops_deployment_risk_linkage
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0183_compliance_risk_recommendations"
down_revision: str | None = "0182_mlops_deployment_risk_linkage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_risk_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("suggested_category", sa.String(length=100), nullable=True),
        sa.Column("suggested_likelihood", sa.Integer(), nullable=True),
        sa.Column("suggested_impact", sa.Integer(), nullable=True),
        sa.Column("suggested_treatment", sa.String(length=100), nullable=True),
        sa.Column("linked_risk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_used", sa.String(length=20), nullable=False),
        sa.Column("used_byo_credentials", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("accepted_risk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismissed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "recommendation_type IN ('gap_identified', 'treatment_change', 'new_risk', 'risk_retirement')",
            name="ck_comp_risk_rec_type",
        ),
        sa.CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_comp_risk_rec_provider"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'dismissed', 'snoozed')", name="ck_comp_risk_rec_status"),
        sa.CheckConstraint(
            "suggested_likelihood IS NULL OR (suggested_likelihood >= 1 AND suggested_likelihood <= 5)",
            name="ck_comp_risk_rec_lh",
        ),
        sa.CheckConstraint(
            "suggested_impact IS NULL OR (suggested_impact >= 1 AND suggested_impact <= 5)",
            name="ck_comp_risk_rec_imp",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_comp_risk_rec_org"),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"], ondelete="SET NULL", name="fk_comp_risk_rec_bu"),
        sa.ForeignKeyConstraint(["linked_risk_id"], ["risks.id"], ondelete="SET NULL", name="fk_comp_risk_rec_link"),
        sa.ForeignKeyConstraint(["accepted_risk_id"], ["risks.id"], ondelete="SET NULL", name="fk_comp_risk_rec_acc"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="RESTRICT", name="fk_comp_risk_rec_gen"),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL", name="fk_comp_risk_rec_aby"),
        sa.ForeignKeyConstraint(["dismissed_by"], ["users.id"], ondelete="SET NULL", name="fk_comp_risk_rec_dby"),
        sa.PrimaryKeyConstraint("id", name="pk_comp_risk_rec"),
    )
    op.create_index(
        "ix_comp_risk_rec_org_status",
        "compliance_risk_recommendations",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_comp_risk_rec_org_type",
        "compliance_risk_recommendations",
        ["organization_id", "recommendation_type"],
        unique=False,
    )
    op.create_index(
        "ix_comp_risk_rec_org_bu",
        "compliance_risk_recommendations",
        ["organization_id", "business_unit_id"],
        unique=False,
    )
    op.create_index(
        "ix_comp_risk_rec_link",
        "compliance_risk_recommendations",
        ["linked_risk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_comp_risk_rec_link", table_name="compliance_risk_recommendations")
    op.drop_index("ix_comp_risk_rec_org_bu", table_name="compliance_risk_recommendations")
    op.drop_index("ix_comp_risk_rec_org_type", table_name="compliance_risk_recommendations")
    op.drop_index("ix_comp_risk_rec_org_status", table_name="compliance_risk_recommendations")
    op.drop_table("compliance_risk_recommendations")
