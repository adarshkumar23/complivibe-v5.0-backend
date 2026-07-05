"""regulatory alerts

Revision ID: 0207_regulatory_alerts
Revises: 0206_sanctions_screening
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0207_regulatory_alerts"
down_revision: str | None = "0206_sanctions_screening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regulatory_change_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_item_id", sa.String(length=128), nullable=False),
        sa.Column("framework_code", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("item_url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'new'")),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("raw_item_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "source_key", "source_item_id", "framework_code", name="uq_reg_alert_org_source_item_fw"),
    )
    op.create_index("ix_reg_alerts_org_status_detected", "regulatory_change_alerts", ["organization_id", "status", "detected_at"], unique=False)
    op.create_index("ix_reg_alerts_source_status", "regulatory_change_alerts", ["source_key", "status"], unique=False)
    op.create_index("ix_reg_alerts_framework_detected", "regulatory_change_alerts", ["framework_code", "detected_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reg_alerts_framework_detected", table_name="regulatory_change_alerts")
    op.drop_index("ix_reg_alerts_source_status", table_name="regulatory_change_alerts")
    op.drop_index("ix_reg_alerts_org_status_detected", table_name="regulatory_change_alerts")
    op.drop_table("regulatory_change_alerts")
