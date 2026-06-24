"""simulation diff reason code fields

Revision ID: 0049_simulation_diff_reason_codes
Revises: 0048_policy_resolution_simulation_diff_reports
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0049_simulation_diff_reason_codes"
down_revision: str | None = "0048_policy_resolution_simulation_diff_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        sa.Column("reason_code_summary_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        sa.Column("reason_code_count", sa.Integer(), nullable=False, server_default="0"),
    )



def downgrade() -> None:
    op.drop_column("ai_system_governance_policy_resolution_simulation_diff_reports", "reason_code_count")
    op.drop_column(
        "ai_system_governance_policy_resolution_simulation_diff_reports",
        "reason_code_summary_json",
    )
