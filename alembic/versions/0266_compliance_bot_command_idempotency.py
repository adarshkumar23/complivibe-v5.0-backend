"""add idempotency key to compliance bot outbox for slash command retries

Revision ID: 0266_compliance_bot_command_idempotency
Revises: 0265_evidence_automation_health_idempotency
Create Date: 2026-07-08

Slack retries a slash command delivery (same trigger_id) when our endpoint
doesn't ack within its timeout window. Without a dedupe key, a retried
"approve" or "urgent" command could re-run mutating side effects (e.g. queue
a second attestation reminder email). This adds an idempotency_key column to
compliance_bot_outbox with a partial unique index so repeated deliveries of
the same command can be detected and replayed from the stored response
instead of re-executed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0266_compliance_bot_command_idempotency"
down_revision: str | None = "0265_evidence_automation_health_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "compliance_bot_outbox",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "uq_compliance_bot_outbox_subscription_idem_key",
        "compliance_bot_outbox",
        ["subscription_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_compliance_bot_outbox_subscription_idem_key", table_name="compliance_bot_outbox")
    op.drop_column("compliance_bot_outbox", "idempotency_key")
