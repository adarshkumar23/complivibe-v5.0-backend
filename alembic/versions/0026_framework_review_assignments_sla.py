"""framework review assignments sla escalation

Revision ID: 0026_framework_review_assignments_sla
Revises: 0025_framework_pack_review_promotion
Create Date: 2026-06-18 17:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0026_framework_review_assignments_sla"
down_revision: str | None = "0025_framework_pack_review_promotion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "framework_pack_review_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="assigned"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_run_id"], ["framework_pack_review_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_pack_review_assignments_org_review",
        "framework_pack_review_assignments",
        ["organization_id", "review_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_framework_pack_review_assignments_org_assignee_status",
        "framework_pack_review_assignments",
        ["organization_id", "assigned_to_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_pack_review_assignments_org_due_at",
        "framework_pack_review_assignments",
        ["organization_id", "due_at"],
        unique=False,
    )

    op.create_table(
        "framework_review_sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("review_type", sa.String(length=32), nullable=False),
        sa.Column("target_coverage_level", sa.String(length=32), nullable=True),
        sa.Column("due_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("escalation_after_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("reminder_before_days", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_review_sla_policies_org_status",
        "framework_review_sla_policies",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_sla_policies_org_review_type",
        "framework_review_sla_policies",
        ["organization_id", "review_type"],
        unique=False,
    )

    op.create_table(
        "framework_review_escalation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_run_id"], ["framework_pack_review_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], ["framework_pack_review_assignments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_framework_review_escalations_org_status",
        "framework_review_escalation_events",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_escalations_org_event_type",
        "framework_review_escalation_events",
        ["organization_id", "event_type"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_escalations_org_review",
        "framework_review_escalation_events",
        ["organization_id", "review_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_framework_review_escalations_org_triggered",
        "framework_review_escalation_events",
        ["organization_id", "triggered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_framework_review_escalations_org_triggered", table_name="framework_review_escalation_events")
    op.drop_index("ix_framework_review_escalations_org_review", table_name="framework_review_escalation_events")
    op.drop_index("ix_framework_review_escalations_org_event_type", table_name="framework_review_escalation_events")
    op.drop_index("ix_framework_review_escalations_org_status", table_name="framework_review_escalation_events")
    op.drop_table("framework_review_escalation_events")

    op.drop_index("ix_framework_review_sla_policies_org_review_type", table_name="framework_review_sla_policies")
    op.drop_index("ix_framework_review_sla_policies_org_status", table_name="framework_review_sla_policies")
    op.drop_table("framework_review_sla_policies")

    op.drop_index("ix_framework_pack_review_assignments_org_due_at", table_name="framework_pack_review_assignments")
    op.drop_index("ix_framework_pack_review_assignments_org_assignee_status", table_name="framework_pack_review_assignments")
    op.drop_index("ix_framework_pack_review_assignments_org_review", table_name="framework_pack_review_assignments")
    op.drop_table("framework_pack_review_assignments")
