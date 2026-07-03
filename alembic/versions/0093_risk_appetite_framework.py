"""risk appetite framework

Revision ID: 0093_risk_appetite_framework
Revises: 0092_key_risk_indicators
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0093_risk_appetite_framework"
down_revision: str | None = "0092_key_risk_indicators"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

scope_type_enum = postgresql.ENUM(
    "org",
    "business_unit",
    name="risk_appetite_scope_type_enum",
    create_type=False,
)

risk_category_enum = postgresql.ENUM(
    "operational",
    "financial",
    "compliance",
    "reputational",
    "technology",
    "vendor",
    name="risk_appetite_category_enum",
    create_type=False,
)


def upgrade() -> None:
    scope_type_enum.create(op.get_bind(), checkfirst=True)
    risk_category_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "risk_appetite_thresholds",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", scope_type_enum, nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_category", risk_category_enum, nullable=False),
        sa.Column("max_acceptable_score", sa.Integer(), nullable=False),
        sa.Column("escalation_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escalation_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_risk_appetite_thresholds_organization_id", "risk_appetite_thresholds", ["organization_id"], unique=False)
    op.create_index(
        "ix_risk_appetite_thresholds_org_active",
        "risk_appetite_thresholds",
        ["organization_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_risk_appetite_thresholds_org_category",
        "risk_appetite_thresholds",
        ["organization_id", "risk_category"],
        unique=False,
    )
    op.create_index(
        "ix_risk_appetite_thresholds_org_scope",
        "risk_appetite_thresholds",
        ["organization_id", "scope_type", "scope_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_risk_appetite_thresholds_org_scope", table_name="risk_appetite_thresholds")
    op.drop_index("ix_risk_appetite_thresholds_org_category", table_name="risk_appetite_thresholds")
    op.drop_index("ix_risk_appetite_thresholds_org_active", table_name="risk_appetite_thresholds")
    op.drop_index("ix_risk_appetite_thresholds_organization_id", table_name="risk_appetite_thresholds")
    op.drop_table("risk_appetite_thresholds")

    risk_category_enum.drop(op.get_bind(), checkfirst=True)
    scope_type_enum.drop(op.get_bind(), checkfirst=True)
