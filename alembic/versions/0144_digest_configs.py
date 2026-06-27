"""digest configs

Revision ID: 0144_digest_configs
Revises: 0143_email_templates_and_notification_preferences
Create Date: 2026-06-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0144_digest_configs"
down_revision: str | None = "0143_email_templates_and_notification_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digest_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("digest_type", sa.String(length=10), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("send_time_utc", sa.String(length=5), nullable=False, server_default=sa.text("'08:00'")),
        sa.Column("send_day_of_week", sa.Integer(), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("digest_type IN ('daily', 'weekly')", name="ck_digest_configs_digest_type"),
        sa.CheckConstraint("send_day_of_week IS NULL OR (send_day_of_week >= 0 AND send_day_of_week <= 6)", name="ck_digest_configs_send_day_of_week"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", "digest_type", name="uq_digest_configs_org_user_type"),
    )
    op.create_index("ix_digest_configs_org_type_enabled", "digest_configs", ["organization_id", "digest_type", "is_enabled"], unique=False)
    op.create_index("ix_digest_configs_user_type", "digest_configs", ["user_id", "digest_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_digest_configs_user_type", table_name="digest_configs")
    op.drop_index("ix_digest_configs_org_type_enabled", table_name="digest_configs")
    op.drop_table("digest_configs")
