"""add compliance bot subscriptions and outbox

Revision ID: 0255_compliance_bot_i2
Revises: 0254_evidence_automation_i1
Create Date: 2026-07-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0255_compliance_bot_i2"
down_revision: str | None = "0254_evidence_automation_i1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_bot_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("channel_ref", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("digest_time_utc", sa.String(length=5), nullable=False, server_default=sa.text("'08:00'")),
        sa.Column("sla_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_digest_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sla_alert_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("platform IN ('slack','teams')", name="ck_compliance_bot_subscriptions_platform"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", "platform", name="uq_compliance_bot_subscriptions_org_user_platform"),
    )
    op.create_index(
        "ix_compliance_bot_subscriptions_org_platform",
        "compliance_bot_subscriptions",
        ["organization_id", "platform"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_bot_subscriptions_org_active",
        "compliance_bot_subscriptions",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "compliance_bot_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("command_text", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "message_type IN ('command_response','daily_digest','sla_alert')",
            name="ck_compliance_bot_outbox_type",
        ),
        sa.CheckConstraint("status IN ('pending','sent','failed')", name="ck_compliance_bot_outbox_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["compliance_bot_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_bot_outbox_org_status",
        "compliance_bot_outbox",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_bot_outbox_org_type",
        "compliance_bot_outbox",
        ["organization_id", "message_type"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_bot_outbox_subscription",
        "compliance_bot_outbox",
        ["subscription_id", "scheduled_for"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_bot_outbox_subscription", table_name="compliance_bot_outbox")
    op.drop_index("ix_compliance_bot_outbox_org_type", table_name="compliance_bot_outbox")
    op.drop_index("ix_compliance_bot_outbox_org_status", table_name="compliance_bot_outbox")
    op.drop_table("compliance_bot_outbox")
    op.drop_index("ix_compliance_bot_subscriptions_org_active", table_name="compliance_bot_subscriptions")
    op.drop_index("ix_compliance_bot_subscriptions_org_platform", table_name="compliance_bot_subscriptions")
    op.drop_table("compliance_bot_subscriptions")
