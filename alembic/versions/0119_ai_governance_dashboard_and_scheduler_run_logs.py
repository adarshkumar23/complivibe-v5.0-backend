"""ai governance dashboard and scheduler run logs

Revision ID: 0119_ai_governance_dashboard_and_scheduler_run_logs
Revises: 0118_regulatory_reports_and_framework_heatmap
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0119_ai_governance_dashboard_and_scheduler_run_logs"
down_revision: str | None = "0118_regulatory_reports_and_framework_heatmap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'running'")),
        sa.Column("records_processed", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_scheduler_run_logs_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduler_run_logs_job_started", "scheduler_run_logs", ["job_name", "started_at"], unique=False)
    op.create_index("ix_scheduler_run_logs_status_started", "scheduler_run_logs", ["status", "started_at"], unique=False)
    op.create_index("ix_scheduler_run_logs_started", "scheduler_run_logs", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scheduler_run_logs_started", table_name="scheduler_run_logs")
    op.drop_index("ix_scheduler_run_logs_status_started", table_name="scheduler_run_logs")
    op.drop_index("ix_scheduler_run_logs_job_started", table_name="scheduler_run_logs")
    op.drop_table("scheduler_run_logs")
