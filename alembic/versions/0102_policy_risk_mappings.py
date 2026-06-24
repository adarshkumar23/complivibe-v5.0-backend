"""policy to risk mappings

Revision ID: 0102_policy_risk_mappings
Revises: 0101_policy_template_library
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0102_policy_risk_mappings"
down_revision: str | None = "0101_policy_template_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_risk_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mitigation_strength", sa.String(length=20), server_default=sa.text("'partial'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("mapped_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mitigation_strength IN ('full', 'partial', 'indirect')",
            name="ck_policy_risk_mappings_mitigation_strength",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mapped_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_risk_mappings_organization_id",
        "policy_risk_mappings",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_risk_mappings_org_policy",
        "policy_risk_mappings",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_risk_mappings_org_risk",
        "policy_risk_mappings",
        ["organization_id", "risk_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_risk_mappings_org_deleted_at",
        "policy_risk_mappings",
        ["organization_id", "deleted_at"],
        unique=False,
    )
    op.create_index(
        "uq_policy_risk_mappings_policy_risk_active",
        "policy_risk_mappings",
        ["policy_id", "risk_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_policy_risk_mappings_policy_risk_active", table_name="policy_risk_mappings")
    op.drop_index("ix_policy_risk_mappings_org_deleted_at", table_name="policy_risk_mappings")
    op.drop_index("ix_policy_risk_mappings_org_risk", table_name="policy_risk_mappings")
    op.drop_index("ix_policy_risk_mappings_org_policy", table_name="policy_risk_mappings")
    op.drop_index("ix_policy_risk_mappings_organization_id", table_name="policy_risk_mappings")
    op.drop_table("policy_risk_mappings")
