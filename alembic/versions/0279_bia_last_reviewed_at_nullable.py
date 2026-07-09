"""make bia_assessments.last_reviewed_at nullable, drop auto-now default

Revision ID: 0272_bia_last_reviewed_at_nullable
Revises: 0271_legal_matter_evidence_control_links
Create Date: 2026-07-08 00:00:00.000000

bia_assessments.last_reviewed_at was NOT NULL with server_default=now(), so every
newly-created BIA was auto-stamped as "reviewed just now" with no reviewed_by_user_id
-- hiding a never-actually-reviewed BIA from overdue-review reports. Make the column
nullable with no default so a freshly-created BIA genuinely shows "never reviewed"
until a real review action sets both last_reviewed_at and reviewed_by_user_id together.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0279_bia_last_reviewed_at_nullable"
down_revision: str | None = "0278_legal_matter_evidence_control_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "bia_assessments",
        "last_reviewed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.execute("UPDATE bia_assessments SET last_reviewed_at = created_at WHERE last_reviewed_at IS NULL")
    op.alter_column(
        "bia_assessments",
        "last_reviewed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
