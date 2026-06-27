"""regulatory reports and framework heatmap

Revision ID: 0118_regulatory_reports_and_framework_heatmap
Revises: 0117_pdf_word_export_and_custom_report_templates
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0118_regulatory_reports_and_framework_heatmap"
down_revision: str | None = "0117_pdf_word_export_and_custom_report_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No schema changes required for A7.5/A7.6.
    pass


def downgrade() -> None:
    pass
