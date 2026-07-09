"""add annual_spend_amount to vendors for spend-weighted HHI concentration risk

Revision ID: 0272_vendor_annual_spend_amount
Revises: 0271_vendor_risk_tier_source
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0276_vendor_annual_spend_amount"
down_revision: str | None = "0275_vendor_risk_tier_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column("annual_spend_amount", sa.Numeric(precision=14, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vendors", "annual_spend_amount")
