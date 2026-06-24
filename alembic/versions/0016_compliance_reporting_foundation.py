"""compliance reporting foundation

Revision ID: 0016_compliance_reporting_foundation
Revises: 0015_recertification_and_scoring_trends
Create Date: 2026-06-18 22:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_compliance_reporting_foundation"
down_revision: Union[str, Sequence[str], None] = "0015_recertification_and_scoring_trends"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_reports",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="generated"),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inputs_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_reports_org_type", "compliance_reports", ["organization_id", "report_type"], unique=False)
    op.create_index("ix_compliance_reports_org_status", "compliance_reports", ["organization_id", "status"], unique=False)
    op.create_index("ix_compliance_reports_org_generated", "compliance_reports", ["organization_id", "generated_at"], unique=False)

    op.create_table(
        "compliance_report_sections",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["compliance_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", "section_key", name="uq_report_section_key"),
    )
    op.create_index("ix_report_sections_org_report", "compliance_report_sections", ["organization_id", "report_id"], unique=False)
    op.create_index("ix_report_sections_sort", "compliance_report_sections", ["report_id", "sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_report_sections_sort", table_name="compliance_report_sections")
    op.drop_index("ix_report_sections_org_report", table_name="compliance_report_sections")
    op.drop_table("compliance_report_sections")

    op.drop_index("ix_compliance_reports_org_generated", table_name="compliance_reports")
    op.drop_index("ix_compliance_reports_org_status", table_name="compliance_reports")
    op.drop_index("ix_compliance_reports_org_type", table_name="compliance_reports")
    op.drop_table("compliance_reports")
