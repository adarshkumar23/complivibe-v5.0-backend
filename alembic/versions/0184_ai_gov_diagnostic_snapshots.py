"""ai governance diagnostic snapshots

Revision ID: 0184_ai_gov_diagnostic_snapshots
Revises: 0183_compliance_risk_recommendations
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0184_ai_gov_diagnostic_snapshots"
down_revision: str | None = "0183_compliance_risk_recommendations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_governance_diagnostic_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_label", sa.String(length=200), nullable=True),
        sa.Column("overall_governance_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("overall_health", sa.String(length=20), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_systems_assessed", sa.Integer(), nullable=False),
        sa.Column("critical_gaps_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "overall_health IN ('good', 'needs_attention', 'at_risk', 'critical')",
            name="ck_ai_gov_diag_health",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_ai_gov_diag_org"),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"], ondelete="SET NULL", name="fk_ai_gov_diag_bu"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="RESTRICT", name="fk_ai_gov_diag_gen"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_gov_diag"),
    )
    op.create_index(
        "ix_ai_gov_diag_org_created",
        "ai_governance_diagnostic_snapshots",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_gov_diag_org_bu",
        "ai_governance_diagnostic_snapshots",
        ["organization_id", "business_unit_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_gov_diag_org_health",
        "ai_governance_diagnostic_snapshots",
        ["organization_id", "overall_health"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_gov_diag_org_health", table_name="ai_governance_diagnostic_snapshots")
    op.drop_index("ix_ai_gov_diag_org_bu", table_name="ai_governance_diagnostic_snapshots")
    op.drop_index("ix_ai_gov_diag_org_created", table_name="ai_governance_diagnostic_snapshots")
    op.drop_table("ai_governance_diagnostic_snapshots")
