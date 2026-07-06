"""add share link password lockout columns

Revision ID: 0246_shared_link_lockout
Revises: 0245_saml_replay
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0246_shared_link_lockout"
down_revision: str | None = "0245_saml_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shared_report_links",
        sa.Column("failed_password_attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "shared_report_links",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shared_report_links", "locked_until")
    op.drop_column("shared_report_links", "failed_password_attempt_count")
