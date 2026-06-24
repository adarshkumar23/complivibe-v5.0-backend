"""compliance policy management foundation

Revision ID: 0082_compliance_policy_management_foundation
Revises: 0081_governance_autopilot_noop_runner_events
Create Date: 2026-06-22 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0082_compliance_policy_management_foundation"
down_revision: str | None = "0081_governance_autopilot_noop_runner_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("policy_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("review_due_date", sa.Date(), nullable=True),
        sa.Column("version", sa.String(length=32), server_default=sa.text("'1.0'"), nullable=False),
        sa.Column("content_url", sa.String(length=512), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_policies_organization_id", "compliance_policies", ["organization_id"], unique=False)
    op.create_index("ix_compliance_policies_org_status", "compliance_policies", ["organization_id", "status"], unique=False)
    op.create_index("ix_compliance_policies_org_type", "compliance_policies", ["organization_id", "policy_type"], unique=False)
    op.create_index(
        "ix_compliance_policies_org_owner",
        "compliance_policies",
        ["organization_id", "owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policies_org_archived",
        "compliance_policies",
        ["organization_id", "archived_at"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policies_org_review_due",
        "compliance_policies",
        ["organization_id", "review_due_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_policies_org_review_due", table_name="compliance_policies")
    op.drop_index("ix_compliance_policies_org_archived", table_name="compliance_policies")
    op.drop_index("ix_compliance_policies_org_owner", table_name="compliance_policies")
    op.drop_index("ix_compliance_policies_org_type", table_name="compliance_policies")
    op.drop_index("ix_compliance_policies_org_status", table_name="compliance_policies")
    op.drop_index("ix_compliance_policies_organization_id", table_name="compliance_policies")
    op.drop_table("compliance_policies")
