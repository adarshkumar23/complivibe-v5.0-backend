"""add last_reviewed_at to controls

Revision ID: 0280_control_last_reviewed_at
Revises: 0279_bia_last_reviewed_at_nullable
Create Date: 2026-07-09 00:00:00.000000

G4 item 2: the CSV/migration-wizard import (ImportJobService) needs somewhere to
persist a "last_reviewed" value parsed from an imported CSV row for controls.
Control had no such column at all, which was part of why the value was silently
dropped on import. Add it nullable with no default -- a freshly-imported or
freshly-created control genuinely has no review history until a real review sets it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0280_control_last_reviewed_at"
down_revision: str | None = "0279_bia_last_reviewed_at_nullable"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "controls",
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("controls", "last_reviewed_at")
