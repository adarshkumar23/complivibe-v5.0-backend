"""batch cancellation dual approval

Revision ID: 0030_batch_cancellation_dual_approval
Revises: 0029_batch_assignment_run_cancellation_governance
Create Date: 2026-06-18 22:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0030_batch_cancellation_dual_approval"
down_revision: str | None = "0029_batch_assignment_run_cancellation_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "framework_review_batch_cancellation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("executed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_run_id"], ["framework_review_batch_assignment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_review_batch_cancel_requests_org_status",
        "framework_review_batch_cancellation_requests",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_batch_cancel_requests_org_run",
        "framework_review_batch_cancellation_requests",
        ["organization_id", "batch_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_batch_cancel_requests_org_requested",
        "framework_review_batch_cancellation_requests",
        ["organization_id", "requested_at"],
        unique=False,
    )

    op.add_column(
        "framework_review_batch_assignment_runs",
        sa.Column("cancellation_requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "framework_review_batch_assignment_runs",
        sa.Column("cancellation_request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_framework_review_batch_assignment_runs_cancellation_request_id",
        "framework_review_batch_assignment_runs",
        "framework_review_batch_cancellation_requests",
        ["cancellation_request_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_framework_review_batch_assignment_runs_cancellation_request_id",
        "framework_review_batch_assignment_runs",
        type_="foreignkey",
    )
    op.drop_column("framework_review_batch_assignment_runs", "cancellation_request_id")
    op.drop_column("framework_review_batch_assignment_runs", "cancellation_requires_approval")

    op.drop_index(
        "ix_framework_review_batch_cancel_requests_org_requested",
        table_name="framework_review_batch_cancellation_requests",
    )
    op.drop_index(
        "ix_framework_review_batch_cancel_requests_org_run",
        table_name="framework_review_batch_cancellation_requests",
    )
    op.drop_index(
        "ix_framework_review_batch_cancel_requests_org_status",
        table_name="framework_review_batch_cancellation_requests",
    )
    op.drop_table("framework_review_batch_cancellation_requests")
