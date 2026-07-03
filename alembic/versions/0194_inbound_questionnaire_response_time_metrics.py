"""inbound questionnaire response time metrics

Revision ID: 0194_inbound_questionnaire_response_time_metrics
Revises: 0193_retention_legal_hold_and_data_obligation_suggestions
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0194_inbound_questionnaire_response_time_metrics"
down_revision: str | None = "0193_retention_legal_hold_and_data_obligation_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbound_questionnaire_sessions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbound_questionnaire_sessions", "completed_at")
