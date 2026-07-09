"""add pbc_items.acceptance_override_reason to require evidence-or-override on accept

Revision ID: 0200_pbc_items_acceptance_override_reason
Revises: 0199_audit_engagement_source_schedule_link
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0200_pbc_items_acceptance_override_reason"
down_revision: str | None = "0199_audit_engagement_source_schedule_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pbc_items",
        sa.Column("acceptance_override_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pbc_items", "acceptance_override_reason")
