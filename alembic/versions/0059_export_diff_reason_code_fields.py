"""export diff reason code fields

Revision ID: 0059_export_diff_reason_code_fields
Revises: 0058_preset_assignment_diagnostic_export_diff_reports
Create Date: 2026-06-20 02:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0059_export_diff_reason_code_fields"
down_revision: str | None = "0058_preset_assignment_diagnostic_export_diff_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        sa.Column("reason_code_summary_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        sa.Column("reason_code_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83", "reason_code_count")
    op.drop_column(
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        "reason_code_summary_json",
    )
