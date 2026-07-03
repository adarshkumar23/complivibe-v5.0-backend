"""org email configs ses delivery

Revision ID: 0174_org_email_configs_ses_delivery
Revises: 0173_billing_razorpay_integration
Create Date: 2026-06-29 23:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0174_org_email_configs_ses_delivery"
down_revision: str | None = "0173_billing_razorpay_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # org_email_configs exists from 0138; this migration extends it for platform/org SES split.
    if _has_table(inspector, "org_email_configs"):
        email_columns: list[tuple[str, sa.Column]] = [
            (
                "use_platform_ses",
                sa.Column("use_platform_ses", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            ),
            ("aws_access_key_id_enc", sa.Column("aws_access_key_id_enc", sa.Text(), nullable=True)),
            ("aws_secret_key_enc", sa.Column("aws_secret_key_enc", sa.Text(), nullable=True)),
            (
                "aws_region",
                sa.Column("aws_region", sa.VARCHAR(length=20), nullable=True, server_default=sa.text("'ap-south-1'")),
            ),
            ("from_email", sa.Column("from_email", sa.VARCHAR(length=255), nullable=True)),
            ("from_name", sa.Column("from_name", sa.VARCHAR(length=100), nullable=True)),
            ("reply_to_email", sa.Column("reply_to_email", sa.VARCHAR(length=255), nullable=True)),
            (
                "daily_send_limit",
                sa.Column("daily_send_limit", sa.Integer(), nullable=False, server_default=sa.text("1000")),
            ),
            ("sent_today", sa.Column("sent_today", sa.Integer(), nullable=False, server_default=sa.text("0"))),
            ("sent_today_reset_at", sa.Column("sent_today_reset_at", sa.DateTime(timezone=True), nullable=True)),
        ]

        for col_name, col in email_columns:
            if not _has_column(inspector, "org_email_configs", col_name):
                op.add_column("org_email_configs", col)
                inspector = sa.inspect(bind)

        # Existing active org configs are custom SES; preserve behavior by defaulting those to non-platform mode.
        if _has_column(inspector, "org_email_configs", "use_platform_ses"):
            op.execute(
                """
                UPDATE org_email_configs
                SET use_platform_ses = false
                WHERE is_active = true
                  AND config_json IS NOT NULL
                """
            )

        if not _has_index(inspector, "org_email_configs", "ix_org_email_configs_org_active"):
            op.create_index(
                "ix_org_email_configs_org_active",
                "org_email_configs",
                ["organization_id", "is_active"],
                unique=False,
            )

    # Add SES-delivery helper fields on existing outbox table if needed.
    inspector = sa.inspect(bind)
    if _has_table(inspector, "email_outbox"):
        if not _has_column(inspector, "email_outbox", "ses_message_id"):
            op.add_column("email_outbox", sa.Column("ses_message_id", sa.VARCHAR(length=100), nullable=True))
        inspector = sa.inspect(bind)
        if not _has_column(inspector, "email_outbox", "retry_count"):
            op.add_column(
                "email_outbox",
                sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "email_outbox"):
        if _has_column(inspector, "email_outbox", "retry_count"):
            op.drop_column("email_outbox", "retry_count")
        inspector = sa.inspect(bind)
        if _has_column(inspector, "email_outbox", "ses_message_id"):
            op.drop_column("email_outbox", "ses_message_id")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "org_email_configs"):
        if _has_index(inspector, "org_email_configs", "ix_org_email_configs_org_active"):
            op.drop_index("ix_org_email_configs_org_active", table_name="org_email_configs")

        for col_name in [
            "sent_today_reset_at",
            "sent_today",
            "daily_send_limit",
            "reply_to_email",
            "from_name",
            "from_email",
            "aws_region",
            "aws_secret_key_enc",
            "aws_access_key_id_enc",
            "use_platform_ses",
        ]:
            inspector = sa.inspect(bind)
            if _has_column(inspector, "org_email_configs", col_name):
                op.drop_column("org_email_configs", col_name)
