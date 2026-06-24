"""framework review batch assignments

Revision ID: 0028_framework_review_batch_assignments
Revises: 0027_framework_review_capacity_and_suggestions
Create Date: 2026-06-18 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0028_framework_review_batch_assignments"
down_revision: str | None = "0027_framework_review_capacity_and_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "framework_review_batch_assignment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="validated"),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("confirmation_text", sa.String(length=128), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applied_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_assignments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notify_assignees", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("validation_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_review_batch_assignment_runs_org_status",
        "framework_review_batch_assignment_runs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_batch_assignment_runs_org_plan_hash",
        "framework_review_batch_assignment_runs",
        ["organization_id", "plan_hash"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_batch_assignment_runs_org_created",
        "framework_review_batch_assignment_runs",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "framework_review_batch_assignment_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skipped_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("scoring_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_run_id"], ["framework_review_batch_assignment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_run_id"], ["framework_pack_review_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_assignment_id"], ["framework_pack_review_assignments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_review_batch_assignment_items_org_run",
        "framework_review_batch_assignment_items",
        ["organization_id", "batch_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_batch_assignment_items_org_status",
        "framework_review_batch_assignment_items",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_batch_assignment_items_org_review_assignee",
        "framework_review_batch_assignment_items",
        ["organization_id", "review_run_id", "assigned_to_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_framework_review_batch_assignment_items_org_review_assignee",
        table_name="framework_review_batch_assignment_items",
    )
    op.drop_index("ix_framework_review_batch_assignment_items_org_status", table_name="framework_review_batch_assignment_items")
    op.drop_index("ix_framework_review_batch_assignment_items_org_run", table_name="framework_review_batch_assignment_items")
    op.drop_table("framework_review_batch_assignment_items")

    op.drop_index("ix_framework_review_batch_assignment_runs_org_created", table_name="framework_review_batch_assignment_runs")
    op.drop_index("ix_framework_review_batch_assignment_runs_org_plan_hash", table_name="framework_review_batch_assignment_runs")
    op.drop_index("ix_framework_review_batch_assignment_runs_org_status", table_name="framework_review_batch_assignment_runs")
    op.drop_table("framework_review_batch_assignment_runs")
