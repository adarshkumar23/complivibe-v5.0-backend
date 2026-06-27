"""general escalation management and breach notification workflow

Revision ID: 0113_general_escalation_and_breach_workflow
Revises: 0112_rca_and_issue_sla_tracking
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0113_general_escalation_and_breach_workflow"
down_revision: str | None = "0112_rca_and_issue_sla_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "escalation_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("condition_type", sa.String(length=50), nullable=False),
        sa.Column("condition_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("escalate_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_message_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entity_type IN ('issue', 'risk', 'vendor_mitigation', 'control_exception', 'pbc_request')",
            name="ck_escalation_policies_entity_type",
        ),
        sa.CheckConstraint(
            "condition_type IN ('time_in_state', 'sla_breach', 'severity_threshold')",
            name="ck_escalation_policies_condition_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escalate_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_escalation_policies_org_entity_active",
        "escalation_policies",
        ["organization_id", "entity_type", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_escalation_policies_org_active",
        "escalation_policies",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "escalation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("escalated_to", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notification_queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["escalation_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escalated_to"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_escalation_events_org_entity",
        "escalation_events",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_escalation_events_policy_entity_escalated",
        "escalation_events",
        ["policy_id", "entity_id", "escalated_at"],
        unique=False,
    )

    op.create_table(
        "breach_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("breach_type", sa.String(length=50), nullable=False),
        sa.Column("personal_data_affected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("estimated_affected_count", sa.Integer(), nullable=True),
        sa.Column("regulatory_notification_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("regulatory_framework", sa.String(length=50), nullable=False, server_default=sa.text("'gdpr'")),
        sa.Column("regulatory_notification_hours", sa.Integer(), nullable=False, server_default=sa.text("72")),
        sa.Column("regulatory_notification_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supervisory_authority", sa.String(length=255), nullable=True),
        sa.Column("regulatory_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject_notification_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("subjects_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'assessing'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "breach_type IN ('personal_data', 'financial', 'health', 'confidential')",
            name="ck_breach_notifications_breach_type",
        ),
        sa.CheckConstraint(
            "regulatory_framework IN ('gdpr', 'hipaa', 'ccpa', 'dpdp', 'pci_dss', 'custom')",
            name="ck_breach_notifications_regulatory_framework",
        ),
        sa.CheckConstraint(
            "status IN ('assessing', 'notification_due', 'regulator_notified', 'subjects_notified', 'closed')",
            name="ck_breach_notifications_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", name="uq_breach_notifications_issue_id"),
    )
    op.create_index("ix_breach_notifications_org_status", "breach_notifications", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_breach_notifications_deadline_status",
        "breach_notifications",
        ["regulatory_notification_deadline", "status"],
        unique=False,
    )
    op.create_index("ix_breach_notifications_org_issue", "breach_notifications", ["organization_id", "issue_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_breach_notifications_org_issue", table_name="breach_notifications")
    op.drop_index("ix_breach_notifications_deadline_status", table_name="breach_notifications")
    op.drop_index("ix_breach_notifications_org_status", table_name="breach_notifications")
    op.drop_table("breach_notifications")

    op.drop_index("ix_escalation_events_policy_entity_escalated", table_name="escalation_events")
    op.drop_index("ix_escalation_events_org_entity", table_name="escalation_events")
    op.drop_table("escalation_events")

    op.drop_index("ix_escalation_policies_org_active", table_name="escalation_policies")
    op.drop_index("ix_escalation_policies_org_entity_active", table_name="escalation_policies")
    op.drop_table("escalation_policies")
