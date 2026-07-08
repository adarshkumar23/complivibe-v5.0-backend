"""enforce single running compliance baseline run per organization

Revision ID: 0265_baseline_run_single_running_guard
Revises: 0264_ai_monitoring_config_baseline_model_version
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0265_baseline_run_single_running_guard"
down_revision: str | None = "0264_ai_monitoring_config_baseline_model_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ux_compliance_baseline_runs_org_running",
        "compliance_baseline_runs",
        ["organization_id"],
        unique=True,
        postgresql_where="status = 'running'",
    )


def downgrade() -> None:
    op.drop_index("ux_compliance_baseline_runs_org_running", table_name="compliance_baseline_runs")
