"""add explainability reason column to escalation_events

Revision ID: 0201_escalation_events_reason_column
Revises: 0200_rca_classification_staleness_snapshots
Create Date: 2026-07-07 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0201_escalation_events_reason_column"
down_revision: str | None = "0200_rca_classification_staleness_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "escalation_events",
        sa.Column("reason", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("escalation_events", "reason")
