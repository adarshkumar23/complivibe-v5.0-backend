"""add webhook delivery idempotency for jira/linear issue sync

Revision ID: 0267_issue_sync_webhook_idempotency
Revises: 0266_compliance_bot_command_idempotency
Create Date: 2026-07-08

Jira and Linear both retry webhook deliveries on timeout/5xx. Without dedupe,
a retried delivery would create a second identical inbound comment on the
linked issue every time. This adds partial unique indexes so retried
deliveries of the same external event / comment can be detected and skipped
instead of reprocessed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0267_issue_sync_webhook_idempotency"
down_revision: str | None = "0266_compliance_bot_command_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_external_sync_events_connection_external_event",
        "external_sync_events",
        ["connection_id", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL AND direction = 'inbound'"),
    )
    op.create_index(
        "uq_issue_sync_comments_issue_provider_external",
        "issue_sync_comments",
        ["issue_id", "provider", "external_comment_id"],
        unique=True,
        postgresql_where=sa.text("external_comment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_issue_sync_comments_issue_provider_external", table_name="issue_sync_comments")
    op.drop_index("uq_external_sync_events_connection_external_event", table_name="external_sync_events")
