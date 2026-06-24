"""applicability answers and deterministic evaluation

Revision ID: 0022_applicability_answers_and_evaluation
Revises: 0021_framework_obligation_content_architecture
Create Date: 2026-06-19 09:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0022_applicability_answers_and_evaluation"
down_revision: Union[str, Sequence[str], None] = "0021_framework_obligation_content_architecture"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_applicability_answers",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("answered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["obligation_applicability_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["answered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_app_answers_org_framework", "organization_applicability_answers", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_org_app_answers_org_question", "organization_applicability_answers", ["organization_id", "question_id"], unique=False)
    op.create_index("ix_org_app_answers_org_status", "organization_applicability_answers", ["organization_id", "status"], unique=False)

    op.create_table(
        "obligation_applicability_rules",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("expected_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_applicability", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["obligation_applicability_questions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obligation_app_rules_framework", "obligation_applicability_rules", ["framework_id"], unique=False)
    op.create_index("ix_obligation_app_rules_obligation", "obligation_applicability_rules", ["obligation_id"], unique=False)
    op.create_index("ix_obligation_app_rules_question", "obligation_applicability_rules", ["question_id"], unique=False)
    op.create_index("ix_obligation_app_rules_status", "obligation_applicability_rules", ["status"], unique=False)

    op.create_table(
        "applicability_evaluation_runs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_obligations_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applicable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_applicable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("states_updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_eval_runs_org_framework", "applicability_evaluation_runs", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_app_eval_runs_org_status", "applicability_evaluation_runs", ["organization_id", "status"], unique=False)

    op.create_table(
        "applicability_evaluation_results",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggested_applicability", sa.String(length=32), nullable=False),
        sa.Column("previous_applicability", sa.String(length=32), nullable=True),
        sa.Column("state_updated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("matched_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_answers_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["applicability_evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_eval_results_org_run", "applicability_evaluation_results", ["organization_id", "evaluation_run_id"], unique=False)
    op.create_index("ix_app_eval_results_org_obligation", "applicability_evaluation_results", ["organization_id", "obligation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_eval_results_org_obligation", table_name="applicability_evaluation_results")
    op.drop_index("ix_app_eval_results_org_run", table_name="applicability_evaluation_results")
    op.drop_table("applicability_evaluation_results")

    op.drop_index("ix_app_eval_runs_org_status", table_name="applicability_evaluation_runs")
    op.drop_index("ix_app_eval_runs_org_framework", table_name="applicability_evaluation_runs")
    op.drop_table("applicability_evaluation_runs")

    op.drop_index("ix_obligation_app_rules_status", table_name="obligation_applicability_rules")
    op.drop_index("ix_obligation_app_rules_question", table_name="obligation_applicability_rules")
    op.drop_index("ix_obligation_app_rules_obligation", table_name="obligation_applicability_rules")
    op.drop_index("ix_obligation_app_rules_framework", table_name="obligation_applicability_rules")
    op.drop_table("obligation_applicability_rules")

    op.drop_index("ix_org_app_answers_org_status", table_name="organization_applicability_answers")
    op.drop_index("ix_org_app_answers_org_question", table_name="organization_applicability_answers")
    op.drop_index("ix_org_app_answers_org_framework", table_name="organization_applicability_answers")
    op.drop_table("organization_applicability_answers")
