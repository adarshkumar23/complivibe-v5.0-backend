"""add truncated flag to draft_requests

/compliance/drafts/policy-content (and the other structured AI-drafting
endpoints) called Azure OpenAI with max_tokens=800, which silently truncated
real policy content (800-1500+ words) mid-sentence with no signal to the
caller. This adds a `truncated` column so create_draft can record whether the
completion was cut off by the token budget (finish_reason == "length"), and
raises the completion token budget itself (see MAX_COMPLETION_TOKENS in
AIDraftingService).

Revision ID: 0271_draft_requests_truncated_flag
Revises: 0270_widen_draft_requests_draft_type
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0271_draft_requests_truncated_flag"
down_revision: str | None = "0270_widen_draft_requests_draft_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "draft_requests",
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("draft_requests", "truncated")
