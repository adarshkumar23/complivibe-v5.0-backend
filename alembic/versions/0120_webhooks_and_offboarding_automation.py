"""webhooks and offboarding automation

Revision ID: 0120_webhooks_and_offboarding_automation
Revises: 0119_ai_governance_dashboard_and_scheduler_run_logs
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0120_webhooks_and_offboarding_automation"
down_revision: str | None = "0119_ai_governance_dashboard_and_scheduler_run_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=False),
        sa.Column("event_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_endpoints_org_active", "webhook_endpoints", ["organization_id", "is_active"], unique=False)

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'failed', 'skipped')", name="ck_webhook_deliveries_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_deliveries_org_status", "webhook_deliveries", ["organization_id", "status"], unique=False)
    op.create_index("ix_webhook_deliveries_endpoint_status", "webhook_deliveries", ["endpoint_id", "status"], unique=False)
    op.create_index("ix_webhook_deliveries_status_created", "webhook_deliveries", ["status", "created_at"], unique=False)

    op.create_table(
        "offboarding_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("default_successor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("require_successor_on_deactivate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_successor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_offboarding_configurations_organization_id"),
    )

    op.create_table(
        "offboarding_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deactivated_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("successor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("records_reassigned", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("total_reassigned", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("executed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deactivated_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["successor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["executed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offboarding_records_org_deactivated_user",
        "offboarding_records",
        ["organization_id", "deactivated_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_offboarding_records_org_deactivated_user", table_name="offboarding_records")
    op.drop_table("offboarding_records")
    op.drop_table("offboarding_configurations")

    op.drop_index("ix_webhook_deliveries_status_created", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_endpoint_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_org_status", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    op.drop_index("ix_webhook_endpoints_org_active", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
