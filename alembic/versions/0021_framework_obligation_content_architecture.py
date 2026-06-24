"""framework obligation content architecture

Revision ID: 0021_framework_obligation_content_architecture
Revises: 0020_override_templates_and_routing
Create Date: 2026-06-19 06:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021_framework_obligation_content_architecture"
down_revision: Union[str, Sequence[str], None] = "0020_override_templates_and_routing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "framework_versions",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("coverage_level", sa.String(length=32), nullable=False, server_default="metadata_only"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_framework_versions_framework_status", "framework_versions", ["framework_id", "status"], unique=False)
    op.create_index("ix_framework_versions_framework_coverage", "framework_versions", ["framework_id", "coverage_level"], unique=False)

    op.create_table(
        "framework_sections",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_version_id"], ["framework_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_section_id"], ["framework_sections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_framework_sections_framework", "framework_sections", ["framework_id"], unique=False)
    op.create_index("ix_framework_sections_framework_version", "framework_sections", ["framework_version_id"], unique=False)
    op.create_index("ix_framework_sections_parent", "framework_sections", ["parent_section_id"], unique=False)
    op.create_index("ix_framework_sections_code", "framework_sections", ["framework_id", "section_code"], unique=False)

    op.add_column("obligations", sa.Column("framework_section_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_obligations_framework_section_id",
        "obligations",
        "framework_sections",
        ["framework_section_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "obligation_content_versions",
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("obligation_text", sa.Text(), nullable=False),
        sa.Column("normalized_summary", sa.Text(), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("coverage_level", sa.String(length=32), nullable=False, server_default="starter"),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_version_id"], ["obligation_content_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obligation_content_versions_obligation", "obligation_content_versions", ["obligation_id"], unique=False)
    op.create_index("ix_obligation_content_versions_review", "obligation_content_versions", ["review_status"], unique=False)

    op.create_table(
        "obligation_applicability_questions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_key", sa.String(length=128), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("answer_type", sa.String(length=32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obligation_questions_framework", "obligation_applicability_questions", ["framework_id"], unique=False)
    op.create_index("ix_obligation_questions_obligation", "obligation_applicability_questions", ["obligation_id"], unique=False)
    op.create_index("ix_obligation_questions_org", "obligation_applicability_questions", ["organization_id"], unique=False)
    op.create_index("ix_obligation_questions_key", "obligation_applicability_questions", ["framework_id", "question_key"], unique=False)

    op.create_table(
        "obligation_evidence_requirements",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("frequency", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obligation_evidence_req_framework", "obligation_evidence_requirements", ["framework_id"], unique=False)
    op.create_index("ix_obligation_evidence_req_obligation", "obligation_evidence_requirements", ["obligation_id"], unique=False)
    op.create_index("ix_obligation_evidence_req_key", "obligation_evidence_requirements", ["obligation_id", "requirement_key"], unique=False)

    op.create_table(
        "obligation_control_suggestions",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_title", sa.String(length=255), nullable=False),
        sa.Column("control_description", sa.Text(), nullable=True),
        sa.Column("control_domain", sa.String(length=128), nullable=True),
        sa.Column("control_type", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obligation_control_suggestions_framework", "obligation_control_suggestions", ["framework_id"], unique=False)
    op.create_index("ix_obligation_control_suggestions_obligation", "obligation_control_suggestions", ["obligation_id"], unique=False)

    op.add_column("controls", sa.Column("suggestion_source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_controls_suggestion_source_id",
        "controls",
        "obligation_control_suggestions",
        ["suggestion_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_controls_suggestion_source_id", "controls", ["suggestion_source_id"], unique=False)

    op.create_table(
        "framework_content_imports",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("import_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("coverage_level", sa.String(length=32), nullable=False, server_default="starter"),
        sa.Column("imported_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_framework_content_imports_framework", "framework_content_imports", ["framework_id"], unique=False)
    op.create_index("ix_framework_content_imports_org", "framework_content_imports", ["organization_id"], unique=False)
    op.create_index("ix_framework_content_imports_status", "framework_content_imports", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_framework_content_imports_status", table_name="framework_content_imports")
    op.drop_index("ix_framework_content_imports_org", table_name="framework_content_imports")
    op.drop_index("ix_framework_content_imports_framework", table_name="framework_content_imports")
    op.drop_table("framework_content_imports")

    op.drop_index("ix_controls_suggestion_source_id", table_name="controls")
    op.drop_constraint("fk_controls_suggestion_source_id", "controls", type_="foreignkey")
    op.drop_column("controls", "suggestion_source_id")

    op.drop_index("ix_obligation_control_suggestions_obligation", table_name="obligation_control_suggestions")
    op.drop_index("ix_obligation_control_suggestions_framework", table_name="obligation_control_suggestions")
    op.drop_table("obligation_control_suggestions")

    op.drop_index("ix_obligation_evidence_req_key", table_name="obligation_evidence_requirements")
    op.drop_index("ix_obligation_evidence_req_obligation", table_name="obligation_evidence_requirements")
    op.drop_index("ix_obligation_evidence_req_framework", table_name="obligation_evidence_requirements")
    op.drop_table("obligation_evidence_requirements")

    op.drop_index("ix_obligation_questions_key", table_name="obligation_applicability_questions")
    op.drop_index("ix_obligation_questions_org", table_name="obligation_applicability_questions")
    op.drop_index("ix_obligation_questions_obligation", table_name="obligation_applicability_questions")
    op.drop_index("ix_obligation_questions_framework", table_name="obligation_applicability_questions")
    op.drop_table("obligation_applicability_questions")

    op.drop_index("ix_obligation_content_versions_review", table_name="obligation_content_versions")
    op.drop_index("ix_obligation_content_versions_obligation", table_name="obligation_content_versions")
    op.drop_table("obligation_content_versions")

    op.drop_constraint("fk_obligations_framework_section_id", "obligations", type_="foreignkey")
    op.drop_column("obligations", "framework_section_id")

    op.drop_index("ix_framework_sections_code", table_name="framework_sections")
    op.drop_index("ix_framework_sections_parent", table_name="framework_sections")
    op.drop_index("ix_framework_sections_framework_version", table_name="framework_sections")
    op.drop_index("ix_framework_sections_framework", table_name="framework_sections")
    op.drop_table("framework_sections")

    op.drop_index("ix_framework_versions_framework_coverage", table_name="framework_versions")
    op.drop_index("ix_framework_versions_framework_status", table_name="framework_versions")
    op.drop_table("framework_versions")
