"""framework review capacity policies workload suggestions

Revision ID: 0027_framework_review_capacity_and_suggestions
Revises: 0026_framework_review_assignments_sla
Create Date: 2026-06-18 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0027_framework_review_capacity_and_suggestions"
down_revision: str | None = "0026_framework_review_assignments_sla"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "framework_reviewer_capacity_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role_name", sa.String(length=120), nullable=True),
        sa.Column("max_active_assignments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_overdue_assignments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preferred_review_types_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preferred_target_coverage_levels_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_reviewer_capacity_policies_org_status",
        "framework_reviewer_capacity_policies",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_reviewer_capacity_policies_org_role",
        "framework_reviewer_capacity_policies",
        ["organization_id", "role_name"],
        unique=False,
    )

    op.create_table(
        "framework_reviewer_workload_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_assignments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_assignments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_assignments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_assignments_last_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_escalations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("workload_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("capacity_remaining", sa.Integer(), nullable=True),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_reviewer_workload_snapshots_org_user",
        "framework_reviewer_workload_snapshots",
        ["organization_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_framework_reviewer_workload_snapshots_org_calculated",
        "framework_reviewer_workload_snapshots",
        ["organization_id", "calculated_at"],
        unique=False,
    )

    op.create_table(
        "framework_review_assignment_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggested_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("scoring_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismissed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_run_id"], ["framework_pack_review_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suggested_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_assignment_id"], ["framework_pack_review_assignments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dismissed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_review_assignment_suggestions_org_review",
        "framework_review_assignment_suggestions",
        ["organization_id", "review_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_assignment_suggestions_org_status",
        "framework_review_assignment_suggestions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_assignment_suggestions_org_review_rank",
        "framework_review_assignment_suggestions",
        ["organization_id", "review_run_id", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_framework_review_assignment_suggestions_org_review_rank",
        table_name="framework_review_assignment_suggestions",
    )
    op.drop_index(
        "ix_framework_review_assignment_suggestions_org_status",
        table_name="framework_review_assignment_suggestions",
    )
    op.drop_index(
        "ix_framework_review_assignment_suggestions_org_review",
        table_name="framework_review_assignment_suggestions",
    )
    op.drop_table("framework_review_assignment_suggestions")

    op.drop_index(
        "ix_framework_reviewer_workload_snapshots_org_calculated",
        table_name="framework_reviewer_workload_snapshots",
    )
    op.drop_index(
        "ix_framework_reviewer_workload_snapshots_org_user",
        table_name="framework_reviewer_workload_snapshots",
    )
    op.drop_table("framework_reviewer_workload_snapshots")

    op.drop_index(
        "ix_framework_reviewer_capacity_policies_org_role",
        table_name="framework_reviewer_capacity_policies",
    )
    op.drop_index(
        "ix_framework_reviewer_capacity_policies_org_status",
        table_name="framework_reviewer_capacity_policies",
    )
    op.drop_table("framework_reviewer_capacity_policies")
