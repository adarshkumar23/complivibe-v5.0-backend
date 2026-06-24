"""email outbox foundation

Revision ID: 0007_email_outbox_foundation
Revises: 0006_control_mapping_layer
Create Date: 2026-06-18 03:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_email_outbox_foundation"
down_revision: Union[str, Sequence[str], None] = "0006_control_mapping_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject_template", sa.Text(), nullable=False),
        sa.Column("body_text_template", sa.Text(), nullable=False),
        sa.Column("body_html_template", sa.Text(), nullable=True),
        sa.Column("allowed_variables_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "template_key", "version", name="uq_email_template_org_key_version"),
    )
    op.create_index("ix_email_templates_template_key", "email_templates", ["template_key"], unique=False)
    op.create_index("ix_email_templates_organization_id", "email_templates", ["organization_id"], unique=False)
    op.create_index("ix_email_templates_status", "email_templates", ["status"], unique=False)

    op.create_table(
        "email_outbox",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["email_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_outbox_organization_id", "email_outbox", ["organization_id"], unique=False)
    op.create_index("ix_email_outbox_status", "email_outbox", ["status"], unique=False)
    op.create_index("ix_email_outbox_event_type", "email_outbox", ["event_type"], unique=False)
    op.create_index("ix_email_outbox_recipient_email", "email_outbox", ["recipient_email"], unique=False)

    op.create_table(
        "email_delivery_events",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email_outbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("status_from", sa.String(length=32), nullable=True),
        sa.Column("status_to", sa.String(length=32), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_outbox_id"], ["email_outbox.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_delivery_events_organization_id", "email_delivery_events", ["organization_id"], unique=False)
    op.create_index("ix_email_delivery_events_outbox_id", "email_delivery_events", ["email_outbox_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_delivery_events_outbox_id", table_name="email_delivery_events")
    op.drop_index("ix_email_delivery_events_organization_id", table_name="email_delivery_events")
    op.drop_table("email_delivery_events")

    op.drop_index("ix_email_outbox_recipient_email", table_name="email_outbox")
    op.drop_index("ix_email_outbox_event_type", table_name="email_outbox")
    op.drop_index("ix_email_outbox_status", table_name="email_outbox")
    op.drop_index("ix_email_outbox_organization_id", table_name="email_outbox")
    op.drop_table("email_outbox")

    op.drop_index("ix_email_templates_status", table_name="email_templates")
    op.drop_index("ix_email_templates_organization_id", table_name="email_templates")
    op.drop_index("ix_email_templates_template_key", table_name="email_templates")
    op.drop_table("email_templates")
