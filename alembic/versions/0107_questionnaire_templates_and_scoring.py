"""questionnaire templates and scoring

Revision ID: 0107_questionnaire_templates_and_scoring
Revises: 0106_audit_scheduling_and_evidence_packages
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0107_questionnaire_templates_and_scoring"
down_revision: str | None = "0106_audit_scheduling_and_evidence_packages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questionnaire_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False, server_default=sa.text("'1.0'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system_template", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("template_type IN ('sig_lite', 'caiq', 'custom')", name="ck_questionnaire_templates_template_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questionnaire_templates_organization_id", "questionnaire_templates", ["organization_id"], unique=False)
    op.create_index(
        "ix_questionnaire_templates_org_active",
        "questionnaire_templates",
        ["organization_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_questionnaire_templates_type_system",
        "questionnaire_templates",
        ["template_type", "is_system_template"],
        unique=False,
    )

    op.create_table(
        "questionnaire_template_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["template_id"], ["questionnaire_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_questionnaire_template_sections_template_order",
        "questionnaire_template_sections",
        ["template_id", "order_index"],
        unique=False,
    )

    op.create_table(
        "questionnaire_template_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("category_tag", sa.String(length=100), nullable=False),
        sa.Column("framework_ref", sa.String(length=255), nullable=True),
        sa.Column("allowed_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expected_answer", sa.String(length=255), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "question_type IN ('yes_no', 'multiple_choice', 'text', 'numeric')",
            name="ck_questionnaire_template_questions_question_type",
        ),
        sa.ForeignKeyConstraint(["template_id"], ["questionnaire_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["questionnaire_template_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_questionnaire_template_questions_template_section_order",
        "questionnaire_template_questions",
        ["template_id", "section_id", "order_index"],
        unique=False,
    )
    op.create_index(
        "ix_questionnaire_template_questions_category_tag",
        "questionnaire_template_questions",
        ["category_tag"],
        unique=False,
    )
    op.create_index(
        "ix_questionnaire_template_questions_framework_ref",
        "questionnaire_template_questions",
        ["framework_ref"],
        unique=False,
    )

    op.create_table(
        "vendor_questionnaire_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_risk_score", sa.Integer(), nullable=True),
        sa.Column("score_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'sent', 'in_progress', 'submitted', 'under_review', 'completed', 'expired')",
            name="ck_vendor_questionnaire_responses_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["questionnaire_templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vendor_questionnaire_responses_org_vendor",
        "vendor_questionnaire_responses",
        ["organization_id", "vendor_id"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_questionnaire_responses_org_status",
        "vendor_questionnaire_responses",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_questionnaire_responses_template_id",
        "vendor_questionnaire_responses",
        ["template_id"],
        unique=False,
    )

    op.create_table(
        "vendor_questionnaire_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_value", sa.String(length=255), nullable=True),
        sa.Column("score_contribution", sa.Integer(), nullable=True),
        sa.Column("is_answered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["response_id"], ["vendor_questionnaire_responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questionnaire_template_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("response_id", "question_id", name="uq_vendor_questionnaire_answers_response_question"),
    )
    op.create_index("ix_vendor_questionnaire_answers_response_id", "vendor_questionnaire_answers", ["response_id"], unique=False)
    op.create_index(
        "ix_vendor_questionnaire_answers_org_response",
        "vendor_questionnaire_answers",
        ["organization_id", "response_id"],
        unique=False,
    )

    op.create_table(
        "questionnaire_scoring_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("condition_operator", sa.String(length=20), nullable=False),
        sa.Column("condition_value", sa.String(length=255), nullable=False),
        sa.Column("score_delta", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "condition_operator IN ('eq', 'ne', 'contains', 'not_contains', 'gte', 'lte')",
            name="ck_questionnaire_scoring_rules_condition_operator",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["questionnaire_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questionnaire_template_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "question_id",
            "condition_operator",
            "condition_value",
            name="uq_questionnaire_scoring_rules_org_question_condition",
        ),
    )
    op.create_index(
        "ix_questionnaire_scoring_rules_template_question",
        "questionnaire_scoring_rules",
        ["template_id", "question_id"],
        unique=False,
    )
    op.create_index(
        "ix_questionnaire_scoring_rules_org_template",
        "questionnaire_scoring_rules",
        ["organization_id", "template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_questionnaire_scoring_rules_org_template", table_name="questionnaire_scoring_rules")
    op.drop_index("ix_questionnaire_scoring_rules_template_question", table_name="questionnaire_scoring_rules")
    op.drop_table("questionnaire_scoring_rules")

    op.drop_index("ix_vendor_questionnaire_answers_org_response", table_name="vendor_questionnaire_answers")
    op.drop_index("ix_vendor_questionnaire_answers_response_id", table_name="vendor_questionnaire_answers")
    op.drop_table("vendor_questionnaire_answers")

    op.drop_index("ix_vendor_questionnaire_responses_template_id", table_name="vendor_questionnaire_responses")
    op.drop_index("ix_vendor_questionnaire_responses_org_status", table_name="vendor_questionnaire_responses")
    op.drop_index("ix_vendor_questionnaire_responses_org_vendor", table_name="vendor_questionnaire_responses")
    op.drop_table("vendor_questionnaire_responses")

    op.drop_index("ix_questionnaire_template_questions_framework_ref", table_name="questionnaire_template_questions")
    op.drop_index("ix_questionnaire_template_questions_category_tag", table_name="questionnaire_template_questions")
    op.drop_index("ix_questionnaire_template_questions_template_section_order", table_name="questionnaire_template_questions")
    op.drop_table("questionnaire_template_questions")

    op.drop_index("ix_questionnaire_template_sections_template_order", table_name="questionnaire_template_sections")
    op.drop_table("questionnaire_template_sections")

    op.drop_index("ix_questionnaire_templates_type_system", table_name="questionnaire_templates")
    op.drop_index("ix_questionnaire_templates_org_active", table_name="questionnaire_templates")
    op.drop_index("ix_questionnaire_templates_organization_id", table_name="questionnaire_templates")
    op.drop_table("questionnaire_templates")
