"""compliance calendar and deadline management

Revision ID: 0091_compliance_calendar_deadline_management
Revises: 0090_control_monitoring_alert_workflow
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0091_compliance_calendar_deadline_management"
down_revision: str | None = "0090_control_monitoring_alert_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_deadlines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deadline_type", sa.String(length=64), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_entity_type", sa.String(length=32), nullable=True),
        sa.Column("linked_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reminder_days_before", sa.Integer(), nullable=False),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        sa.Column("waiver_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_deadlines_organization_id", "compliance_deadlines", ["organization_id"], unique=False)
    op.create_index("ix_compliance_deadlines_org_status", "compliance_deadlines", ["organization_id", "status"], unique=False)
    op.create_index("ix_compliance_deadlines_org_type", "compliance_deadlines", ["organization_id", "deadline_type"], unique=False)
    op.create_index("ix_compliance_deadlines_org_priority", "compliance_deadlines", ["organization_id", "priority"], unique=False)
    op.create_index("ix_compliance_deadlines_org_owner", "compliance_deadlines", ["organization_id", "owner_user_id"], unique=False)
    op.create_index("ix_compliance_deadlines_org_due_date", "compliance_deadlines", ["organization_id", "due_date"], unique=False)
    op.create_index("ix_compliance_deadlines_org_linked", "compliance_deadlines", ["organization_id", "linked_entity_type", "linked_entity_id"], unique=False)

    op.create_table(
        "compliance_deadline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deadline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("outbox_queued", sa.Boolean(), nullable=False),
        sa.Column("event_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deadline_id"], ["compliance_deadlines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_deadline_events_organization_id", "compliance_deadline_events", ["organization_id"], unique=False)
    op.create_index("ix_compliance_deadline_events_org_deadline", "compliance_deadline_events", ["organization_id", "deadline_id"], unique=False)
    op.create_index("ix_compliance_deadline_events_org_type", "compliance_deadline_events", ["organization_id", "event_type"], unique=False)
    op.create_index("ix_compliance_deadline_events_org_created", "compliance_deadline_events", ["organization_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_compliance_deadline_events_org_created", table_name="compliance_deadline_events")
    op.drop_index("ix_compliance_deadline_events_org_type", table_name="compliance_deadline_events")
    op.drop_index("ix_compliance_deadline_events_org_deadline", table_name="compliance_deadline_events")
    op.drop_index("ix_compliance_deadline_events_organization_id", table_name="compliance_deadline_events")
    op.drop_table("compliance_deadline_events")

    op.drop_index("ix_compliance_deadlines_org_linked", table_name="compliance_deadlines")
    op.drop_index("ix_compliance_deadlines_org_due_date", table_name="compliance_deadlines")
    op.drop_index("ix_compliance_deadlines_org_owner", table_name="compliance_deadlines")
    op.drop_index("ix_compliance_deadlines_org_priority", table_name="compliance_deadlines")
    op.drop_index("ix_compliance_deadlines_org_type", table_name="compliance_deadlines")
    op.drop_index("ix_compliance_deadlines_org_status", table_name="compliance_deadlines")
    op.drop_index("ix_compliance_deadlines_organization_id", table_name="compliance_deadlines")
    op.drop_table("compliance_deadlines")
