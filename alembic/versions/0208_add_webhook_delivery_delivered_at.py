"""add webhook delivery delivered_at

Revision ID: 0208_add_webhook_delivery_delivered_at
Revises: 0207_regulatory_alerts
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0208_add_webhook_delivery_delivered_at"
down_revision: str | None = "0207_regulatory_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_deliveries",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webhook_deliveries", "delivered_at")
