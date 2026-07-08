"""add risk_tier_source provenance column to vendors

Revision ID: 0271_vendor_risk_tier_source
Revises: 0270_vendor_assessment_staleness
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0271_vendor_risk_tier_source"
down_revision: str | None = "0270_vendor_assessment_staleness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column(
            "risk_tier_source",
            sa.String(length=32),
            nullable=False,
            server_default="computed",
        ),
    )


def downgrade() -> None:
    op.drop_column("vendors", "risk_tier_source")
