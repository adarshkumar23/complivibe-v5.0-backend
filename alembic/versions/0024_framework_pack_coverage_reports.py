"""framework pack coverage reports

Revision ID: 0024_framework_pack_coverage_reports
Revises: 0023_obligation_control_recommendations
Create Date: 2026-06-19 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0024_framework_pack_coverage_reports"
down_revision: Union[str, Sequence[str], None] = "0023_obligation_control_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "framework_pack_coverage_reports",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pack_key", sa.String(length=128), nullable=False),
        sa.Column("coverage_level", sa.String(length=32), nullable=False, server_default="starter"),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"),
        sa.Column("total_sections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_obligations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("obligations_with_content", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("obligations_with_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("obligations_with_evidence_requirements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("obligations_with_control_suggestions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_content_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_evidence_requirement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_control_suggestion_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_version_id"], ["framework_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_framework_pack_cov_framework", "framework_pack_coverage_reports", ["framework_id"], unique=False)
    op.create_index("ix_framework_pack_cov_framework_version", "framework_pack_coverage_reports", ["framework_version_id"], unique=False)
    op.create_index("ix_framework_pack_cov_pack_key", "framework_pack_coverage_reports", ["pack_key"], unique=False)
    op.create_index("ix_framework_pack_cov_generated_at", "framework_pack_coverage_reports", ["generated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_framework_pack_cov_generated_at", table_name="framework_pack_coverage_reports")
    op.drop_index("ix_framework_pack_cov_pack_key", table_name="framework_pack_coverage_reports")
    op.drop_index("ix_framework_pack_cov_framework_version", table_name="framework_pack_coverage_reports")
    op.drop_index("ix_framework_pack_cov_framework", table_name="framework_pack_coverage_reports")
    op.drop_table("framework_pack_coverage_reports")
