"""policy template library and policy-risk links refresh

Revision ID: 0186_policy_templates_risk_links
Revises: 0185_attestations_policy_exceptions_refresh
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0186_policy_templates_risk_links"
down_revision: str | None = "0185_attestations_policy_exceptions_refresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("policy_templates", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("policy_templates", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("policy_templates", sa.Column("policy_type", sa.String(length=100), nullable=True))
    op.add_column(
        "policy_templates",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_foreign_key(
        "fk_policy_templates_org_id",
        "policy_templates",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_policy_templates_organization_id", "policy_templates", ["organization_id"], unique=False)
    op.create_index("ix_policy_templates_policy_type", "policy_templates", ["policy_type"], unique=False)
    op.create_index("ix_policy_templates_is_system_is_active", "policy_templates", ["is_system", "is_active"], unique=False)

    op.execute("UPDATE policy_templates SET title = name WHERE title IS NULL")
    op.execute("UPDATE policy_templates SET is_system = true")
    op.execute(
        """
        UPDATE policy_templates
        SET policy_type = CASE
            WHEN slug IN ('data-retention', 'data-classification') THEN 'data_privacy'
            WHEN slug IN ('access-control', 'password-management') THEN 'access_control'
            WHEN slug = 'incident-response' THEN 'incident_response'
            WHEN slug = 'vendor-management' THEN 'vendor_management'
            WHEN slug = 'business-continuity' THEN 'business_continuity'
            WHEN slug IN ('change-management', 'whistleblower-ethics') THEN 'change_management'
            WHEN slug = 'acceptable-use' THEN 'acceptable_use'
            WHEN slug IN ('information-security', 'remote-work', 'secure-development') THEN 'information_security'
            WHEN slug = 'ai-governance' THEN 'ai_governance'
            WHEN slug = 'third-party-risk' THEN 'third_party_risk'
            ELSE 'information_security'
        END
        WHERE policy_type IS NULL
        """
    )

    op.create_table(
        "policy_risk_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlink_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unlinked_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "risk_id", name="uq_policy_risk_links_policy_risk"),
    )
    op.create_index("ix_policy_risk_links_org_policy", "policy_risk_links", ["organization_id", "policy_id"], unique=False)
    op.create_index("ix_policy_risk_links_org_risk", "policy_risk_links", ["organization_id", "risk_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_policy_risk_links_org_risk", table_name="policy_risk_links")
    op.drop_index("ix_policy_risk_links_org_policy", table_name="policy_risk_links")
    op.drop_table("policy_risk_links")

    op.drop_index("ix_policy_templates_is_system_is_active", table_name="policy_templates")
    op.drop_index("ix_policy_templates_policy_type", table_name="policy_templates")
    op.drop_index("ix_policy_templates_organization_id", table_name="policy_templates")
    op.drop_constraint("fk_policy_templates_org_id", "policy_templates", type_="foreignkey")
    op.drop_column("policy_templates", "is_system")
    op.drop_column("policy_templates", "policy_type")
    op.drop_column("policy_templates", "title")
    op.drop_column("policy_templates", "organization_id")
