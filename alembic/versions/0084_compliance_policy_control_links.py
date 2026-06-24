"""compliance policy control links

Revision ID: 0084_compliance_policy_control_links
Revises: 0083_compliance_policy_version_control_and_approval
Create Date: 2026-06-22 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0084_compliance_policy_control_links"
down_revision: str | None = "0083_compliance_policy_version_control_and_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_policy_control_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlink_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unlinked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_policy_control_links_organization_id",
        "compliance_policy_control_links",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_control_links_org_policy",
        "compliance_policy_control_links",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_control_links_org_control",
        "compliance_policy_control_links",
        ["organization_id", "control_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_control_links_org_status",
        "compliance_policy_control_links",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_control_links_org_created",
        "compliance_policy_control_links",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_policy_control_links_org_created", table_name="compliance_policy_control_links")
    op.drop_index("ix_compliance_policy_control_links_org_status", table_name="compliance_policy_control_links")
    op.drop_index("ix_compliance_policy_control_links_org_control", table_name="compliance_policy_control_links")
    op.drop_index("ix_compliance_policy_control_links_org_policy", table_name="compliance_policy_control_links")
    op.drop_index("ix_compliance_policy_control_links_organization_id", table_name="compliance_policy_control_links")
    op.drop_table("compliance_policy_control_links")
