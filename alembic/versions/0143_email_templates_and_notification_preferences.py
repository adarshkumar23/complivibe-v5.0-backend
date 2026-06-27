"""email templates and notification preferences

Revision ID: 0143_email_templates_and_notification_preferences
Revises: 0142_dpa_tracking_and_breach_privacy_extension
Create Date: 2026-06-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0143_email_templates_and_notification_preferences"
down_revision: str | None = "0142_dpa_tracking_and_breach_privacy_extension"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("email_outbox", sa.Column("template_name", sa.String(length=120), nullable=True))
    op.add_column("email_outbox", sa.Column("template_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "user_notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default=sa.text("'email'")),
        sa.Column("min_severity", sa.String(length=20), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("channel IN ('email', 'in_app', 'none')", name="ck_user_notification_preferences_channel"),
        sa.CheckConstraint("min_severity IS NULL OR min_severity IN ('critical', 'high', 'medium', 'low')", name="ck_user_notification_preferences_min_severity"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "notification_type",
            name="uq_user_notification_preferences_org_user_type",
        ),
    )
    op.create_index(
        "ix_user_notification_preferences_org_user",
        "user_notification_preferences",
        ["organization_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_notification_preferences_user_type_enabled",
        "user_notification_preferences",
        ["user_id", "notification_type", "is_enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_notification_preferences_user_type_enabled", table_name="user_notification_preferences")
    op.drop_index("ix_user_notification_preferences_org_user", table_name="user_notification_preferences")
    op.drop_table("user_notification_preferences")

    op.drop_column("email_outbox", "template_context")
    op.drop_column("email_outbox", "template_name")
