"""pdf/word export and custom report templates

Revision ID: 0117_pdf_word_export_and_custom_report_templates
Revises: 0116_board_scorecard_and_executive_narrative
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0117_pdf_word_export_and_custom_report_templates"
down_revision: str | None = "0116_board_scorecard_and_executive_narrative"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_report_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("framework_filter", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("date_range_days", sa.Integer(), nullable=False, server_default=sa.text("90")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_custom_report_templates_org_created_by",
        "custom_report_templates",
        ["organization_id", "created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_custom_report_templates_org_created_by", table_name="custom_report_templates")
    op.drop_table("custom_report_templates")
