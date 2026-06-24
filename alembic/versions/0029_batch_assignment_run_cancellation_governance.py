"""batch assignment run cancellation governance

Revision ID: 0029_batch_assignment_run_cancellation_governance
Revises: 0028_framework_review_batch_assignments
Create Date: 2026-06-18 21:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0029_batch_assignment_run_cancellation_governance"
down_revision: str | None = "0028_framework_review_batch_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "framework_review_batch_assignment_runs",
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "framework_review_batch_assignment_runs",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "framework_review_batch_assignment_runs",
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "framework_review_batch_assignment_runs",
        sa.Column("cancellation_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_framework_review_batch_assignment_runs_cancelled_by_user_id_users",
        "framework_review_batch_assignment_runs",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_framework_review_batch_assignment_runs_cancelled_by_user_id_users",
        "framework_review_batch_assignment_runs",
        type_="foreignkey",
    )
    op.drop_column("framework_review_batch_assignment_runs", "cancellation_metadata_json")
    op.drop_column("framework_review_batch_assignment_runs", "cancellation_reason")
    op.drop_column("framework_review_batch_assignment_runs", "cancelled_at")
    op.drop_column("framework_review_batch_assignment_runs", "cancelled_by_user_id")
