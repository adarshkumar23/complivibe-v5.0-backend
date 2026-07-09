"""add tasks.escalation_tier so the reminder job stops clobbering priority

Revision ID: 0280_task_escalation_tier
Revises: 0279_bia_last_reviewed_at_nullable
Create Date: 2026-07-09 00:00:00.000000

The overdue-task reminder job (POST /tasks/reminders/queue) computed an
escalation tier from how many days a task was overdue and wrote it directly
into `tasks.priority` -- silently overwriting whatever priority the task's
owner/creator had deliberately set. A user-set "low" priority task would get
bumped to "urgent" by the background job with no way to tell the difference
between an intentional priority and a job-computed one, and the original
value was gone. This adds a distinct `escalation_tier` column for the job to
write to, leaving `priority` exclusively user-controlled.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0281_task_escalation_tier"
down_revision: str | None = "0280_control_last_reviewed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("escalation_tier", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "escalation_tier")
