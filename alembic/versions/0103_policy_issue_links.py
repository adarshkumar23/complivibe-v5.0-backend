"""policy to issue links

Revision ID: 0103_policy_issue_links
Revises: 0102_policy_risk_mappings
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0103_policy_issue_links"
down_revision: str | None = "0102_policy_risk_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_issue_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("violation_type", sa.String(length=50), server_default=sa.text("'violation'"), nullable=False),
        sa.Column("severity_impact", sa.String(length=20), server_default=sa.text("'medium'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "violation_type IN ('violation', 'near_miss', 'observation', 'procedural_gap')",
            name="ck_policy_issue_links_violation_type",
        ),
        sa.CheckConstraint(
            "severity_impact IN ('low', 'medium', 'high', 'critical')",
            name="ck_policy_issue_links_severity_impact",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_issue_links_organization_id",
        "policy_issue_links",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_issue_links_org_policy",
        "policy_issue_links",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_issue_links_org_issue",
        "policy_issue_links",
        ["organization_id", "issue_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_issue_links_org_violation_type",
        "policy_issue_links",
        ["organization_id", "violation_type"],
        unique=False,
    )
    op.create_index(
        "ix_policy_issue_links_org_deleted_at",
        "policy_issue_links",
        ["organization_id", "deleted_at"],
        unique=False,
    )
    op.create_index(
        "uq_policy_issue_links_policy_issue_active",
        "policy_issue_links",
        ["policy_id", "issue_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_policy_issue_links_policy_issue_active", table_name="policy_issue_links")
    op.drop_index("ix_policy_issue_links_org_deleted_at", table_name="policy_issue_links")
    op.drop_index("ix_policy_issue_links_org_violation_type", table_name="policy_issue_links")
    op.drop_index("ix_policy_issue_links_org_issue", table_name="policy_issue_links")
    op.drop_index("ix_policy_issue_links_org_policy", table_name="policy_issue_links")
    op.drop_index("ix_policy_issue_links_organization_id", table_name="policy_issue_links")
    op.drop_table("policy_issue_links")
