"""audit planning and pbc items

Revision ID: 0104_audit_planning_and_pbc_items
Revises: 0103_policy_issue_links
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0104_audit_planning_and_pbc_items"
down_revision: str | None = "0103_policy_issue_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_engagements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audit_type", sa.String(length=50), nullable=False),
        sa.Column("scope_framework_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("assigned_auditor_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'planning'")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("report_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_auditor_name", sa.String(length=255), nullable=True),
        sa.Column("audit_firm", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "audit_type IN ('internal_readiness', 'external_certification', 'surveillance', 'gap_assessment')",
            name="ck_audit_engagements_audit_type",
        ),
        sa.CheckConstraint(
            "status IN ('planning', 'fieldwork', 'review', 'report_issuance', 'closed', 'cancelled')",
            name="ck_audit_engagements_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_audit_engagements_date_range"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_engagements_organization_id", "audit_engagements", ["organization_id"], unique=False)
    op.create_index("ix_audit_engagements_org_status", "audit_engagements", ["organization_id", "status"], unique=False)
    op.create_index("ix_audit_engagements_org_audit_type", "audit_engagements", ["organization_id", "audit_type"], unique=False)
    op.create_index("ix_audit_engagements_org_start_date", "audit_engagements", ["organization_id", "start_date"], unique=False)

    op.create_table(
        "pbc_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_engagement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'submitted', 'accepted', 'rejected', 'overdue')",
            name="ck_pbc_items_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_engagement_id"], ["audit_engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pbc_items_organization_id", "pbc_items", ["organization_id"], unique=False)
    op.create_index("ix_pbc_items_org_engagement", "pbc_items", ["organization_id", "audit_engagement_id"], unique=False)
    op.create_index("ix_pbc_items_org_status", "pbc_items", ["organization_id", "status"], unique=False)
    op.create_index("ix_pbc_items_assignee_due_date", "pbc_items", ["assignee_id", "due_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pbc_items_assignee_due_date", table_name="pbc_items")
    op.drop_index("ix_pbc_items_org_status", table_name="pbc_items")
    op.drop_index("ix_pbc_items_org_engagement", table_name="pbc_items")
    op.drop_index("ix_pbc_items_organization_id", table_name="pbc_items")
    op.drop_table("pbc_items")

    op.drop_index("ix_audit_engagements_org_start_date", table_name="audit_engagements")
    op.drop_index("ix_audit_engagements_org_audit_type", table_name="audit_engagements")
    op.drop_index("ix_audit_engagements_org_status", table_name="audit_engagements")
    op.drop_index("ix_audit_engagements_organization_id", table_name="audit_engagements")
    op.drop_table("audit_engagements")
