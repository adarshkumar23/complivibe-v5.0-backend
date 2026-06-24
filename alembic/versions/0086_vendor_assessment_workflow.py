"""vendor assessment workflow

Revision ID: 0086_vendor_assessment_workflow
Revises: 0085_vendor_third_party_risk_foundation
Create Date: 2026-06-22 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0086_vendor_assessment_workflow"
down_revision: str | None = "0085_vendor_third_party_risk_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("assessment_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("findings_summary", sa.Text(), nullable=True),
        sa.Column("overall_rating", sa.String(length=32), nullable=False, server_default=sa.text("'not_rated'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_assessments_organization_id", "vendor_assessments", ["organization_id"], unique=False)
    op.create_index("ix_vendor_assessments_org_vendor", "vendor_assessments", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_assessments_org_status", "vendor_assessments", ["organization_id", "status"], unique=False)
    op.create_index("ix_vendor_assessments_org_type", "vendor_assessments", ["organization_id", "assessment_type"], unique=False)
    op.create_index("ix_vendor_assessments_org_assignee", "vendor_assessments", ["organization_id", "assigned_to_user_id"], unique=False)
    op.create_index("ix_vendor_assessments_org_due", "vendor_assessments", ["organization_id", "due_date"], unique=False)

    op.create_table(
        "vendor_assessment_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_text", sa.String(length=500), nullable=False),
        sa.Column("question_category", sa.String(length=32), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_status", sa.String(length=32), nullable=False),
        sa.Column("answered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["vendor_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["answered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_assessment_questions_organization_id", "vendor_assessment_questions", ["organization_id"], unique=False)
    op.create_index("ix_vendor_assessment_questions_org_assessment", "vendor_assessment_questions", ["organization_id", "assessment_id"], unique=False)
    op.create_index("ix_vendor_assessment_questions_org_category", "vendor_assessment_questions", ["organization_id", "question_category"], unique=False)
    op.create_index("ix_vendor_assessment_questions_org_response", "vendor_assessment_questions", ["organization_id", "response_status"], unique=False)
    op.create_index("ix_vendor_assessment_questions_org_sort", "vendor_assessment_questions", ["organization_id", "assessment_id", "sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendor_assessment_questions_org_sort", table_name="vendor_assessment_questions")
    op.drop_index("ix_vendor_assessment_questions_org_response", table_name="vendor_assessment_questions")
    op.drop_index("ix_vendor_assessment_questions_org_category", table_name="vendor_assessment_questions")
    op.drop_index("ix_vendor_assessment_questions_org_assessment", table_name="vendor_assessment_questions")
    op.drop_index("ix_vendor_assessment_questions_organization_id", table_name="vendor_assessment_questions")
    op.drop_table("vendor_assessment_questions")

    op.drop_index("ix_vendor_assessments_org_due", table_name="vendor_assessments")
    op.drop_index("ix_vendor_assessments_org_assignee", table_name="vendor_assessments")
    op.drop_index("ix_vendor_assessments_org_type", table_name="vendor_assessments")
    op.drop_index("ix_vendor_assessments_org_status", table_name="vendor_assessments")
    op.drop_index("ix_vendor_assessments_org_vendor", table_name="vendor_assessments")
    op.drop_index("ix_vendor_assessments_organization_id", table_name="vendor_assessments")
    op.drop_table("vendor_assessments")
