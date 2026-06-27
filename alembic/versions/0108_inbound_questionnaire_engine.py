"""deterministic inbound questionnaire response engine

Revision ID: 0108_inbound_questionnaire_engine
Revises: 0107_questionnaire_templates_and_scoring
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0108_inbound_questionnaire_engine"
down_revision: str | None = "0107_questionnaire_templates_and_scoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_certifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("certification_type", sa.String(length=100), nullable=False, server_default=sa.text("'other'")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'inactive', 'draft')",
            name="ck_compliance_certifications_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_certifications_org_status",
        "compliance_certifications",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_certifications_org_name",
        "compliance_certifications",
        ["organization_id", "name"],
        unique=False,
    )

    op.create_table(
        "inbound_questionnaire_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("sender_name", sa.String(length=255), nullable=False),
        sa.Column("sender_email", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("drafted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("approved_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'under_review', 'completed', 'archived')",
            name="ck_inbound_questionnaire_sessions_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inbound_questionnaire_sessions_org_status",
        "inbound_questionnaire_sessions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_questionnaire_sessions_org_due_date",
        "inbound_questionnaire_sessions",
        ["organization_id", "due_date"],
        unique=False,
    )

    op.create_table(
        "inbound_questionnaire_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False, server_default=sa.text("'text'")),
        sa.Column("category_tag", sa.String(length=100), nullable=True),
        sa.Column("framework_ref", sa.String(length=255), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("suggested_answer_text", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_title", sa.String(length=255), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("final_answer_text", sa.Text(), nullable=True),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "question_type IN ('yes_no', 'text', 'multiple_choice', 'numeric')",
            name="ck_inbound_questionnaire_items_question_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('evidence', 'control', 'certification', 'policy', 'previous_answer') OR source_type IS NULL",
            name="ck_inbound_questionnaire_items_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'drafted', 'needs_review', 'approved', 'rejected', 'sent')",
            name="ck_inbound_questionnaire_items_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["inbound_questionnaire_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbound_questionnaire_items_session_id", "inbound_questionnaire_items", ["session_id"], unique=False)
    op.create_index(
        "ix_inbound_questionnaire_items_org_status",
        "inbound_questionnaire_items",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_questionnaire_items_category_tag",
        "inbound_questionnaire_items",
        ["category_tag"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_questionnaire_items_category_tag", table_name="inbound_questionnaire_items")
    op.drop_index("ix_inbound_questionnaire_items_org_status", table_name="inbound_questionnaire_items")
    op.drop_index("ix_inbound_questionnaire_items_session_id", table_name="inbound_questionnaire_items")
    op.drop_table("inbound_questionnaire_items")

    op.drop_index("ix_inbound_questionnaire_sessions_org_due_date", table_name="inbound_questionnaire_sessions")
    op.drop_index("ix_inbound_questionnaire_sessions_org_status", table_name="inbound_questionnaire_sessions")
    op.drop_table("inbound_questionnaire_sessions")

    op.drop_index("ix_compliance_certifications_org_name", table_name="compliance_certifications")
    op.drop_index("ix_compliance_certifications_org_status", table_name="compliance_certifications")
    op.drop_table("compliance_certifications")
