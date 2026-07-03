"""ai system governance review scheduling and reminders

Revision ID: 0039_ai_system_governance_review_scheduling
Revises: 0038_ai_system_governance_reviews_attestations
Create Date: 2026-06-19 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0039_ai_system_governance_review_scheduling"
down_revision: str | None = "0038_ai_system_governance_reviews_attestations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_review_reminder_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=True),
        sa.Column("days_before_due", sa.Integer(), nullable=False),
        sa.Column("overdue_after_days", sa.Integer(), nullable=False),
        sa.Column("escalation_after_days", sa.Integer(), nullable=False),
        sa.Column("notify_assignee", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_review_reminder_policies_org_id_8bfe8506",
        "ai_system_governance_review_reminder_policies",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_reminder_policies_org_status",
        "ai_system_governance_review_reminder_policies",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_reminder_policies_org_review_type",
        "ai_system_governance_review_reminder_policies",
        ["organization_id", "review_type"],
        unique=False,
    )

    op.add_column("ai_system_governance_reviews", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "ai_system_governance_reviews",
        sa.Column("reminder_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_reviews",
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("ai_system_governance_reviews", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_ai_system_governance_reviews_reminder_policy_id",
        "ai_system_governance_reviews",
        "ai_system_governance_review_reminder_policies",
        ["reminder_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_system_gov_reviews_org_due_at",
        "ai_system_governance_reviews",
        ["organization_id", "due_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_reviews_org_reminder_policy",
        "ai_system_governance_reviews",
        ["organization_id", "reminder_policy_id"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_id"], ["ai_system_governance_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_review_events_organization_id",
        "ai_system_governance_review_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_events_org_status",
        "ai_system_governance_review_events",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_events_org_event_type",
        "ai_system_governance_review_events",
        ["organization_id", "event_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_events_org_review",
        "ai_system_governance_review_events",
        ["organization_id", "review_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_review_events_org_triggered",
        "ai_system_governance_review_events",
        ["organization_id", "triggered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_sys_gov_review_events_org_triggered", table_name="ai_system_governance_review_events")
    op.drop_index("ix_ai_sys_gov_review_events_org_review", table_name="ai_system_governance_review_events")
    op.drop_index("ix_ai_sys_gov_review_events_org_event_type", table_name="ai_system_governance_review_events")
    op.drop_index("ix_ai_sys_gov_review_events_org_status", table_name="ai_system_governance_review_events")
    op.drop_index("ix_ai_system_governance_review_events_organization_id", table_name="ai_system_governance_review_events")
    op.drop_table("ai_system_governance_review_events")

    op.drop_index("ix_ai_system_gov_reviews_org_reminder_policy", table_name="ai_system_governance_reviews")
    op.drop_index("ix_ai_system_gov_reviews_org_due_at", table_name="ai_system_governance_reviews")
    op.drop_constraint("fk_ai_system_governance_reviews_reminder_policy_id", "ai_system_governance_reviews", type_="foreignkey")
    op.drop_column("ai_system_governance_reviews", "escalated_at")
    op.drop_column("ai_system_governance_reviews", "last_reminder_at")
    op.drop_column("ai_system_governance_reviews", "reminder_policy_id")
    op.drop_column("ai_system_governance_reviews", "due_at")

    op.drop_index(
        "ix_ai_sys_gov_review_reminder_policies_org_review_type",
        table_name="ai_system_governance_review_reminder_policies",
    )
    op.drop_index(
        "ix_ai_sys_gov_review_reminder_policies_org_status",
        table_name="ai_system_governance_review_reminder_policies",
    )
    op.drop_index(
        "ix_ai_system_gov_review_reminder_policies_org_id_8bfe8506",
        table_name="ai_system_governance_review_reminder_policies",
    )
    op.drop_table("ai_system_governance_review_reminder_policies")
