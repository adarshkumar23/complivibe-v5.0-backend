"""geopolitical risk -> vendor risk_tier / risk-register cascade

Revision ID: 0291_geopolitical_risk_vendor_cascade
Revises: 0290_vendor_intel_score_confidence
Create Date: 2026-07-09 00:00:00.000000

Root-cause fix for G6 item 3: Geopolitical Risk Monitoring generated real
signals/alerts, but they only ever lived in their own dashboard -- a critical
geopolitical signal about a vendor's operating region never actually affected that
vendor's risk_tier or created a Risk register entry, no matter how severe.

Adds tracking columns to `vendor_geopolitical_exposure` so
`GeopoliticalRiskService` can cascade a critical signal into a real Risk exactly
once per vendor/region exposure (idempotent -- re-ingesting more critical signals
for a region that already has an open cascade risk does not spam duplicate Risk
rows), while still re-checking/escalating the vendor's risk_tier every time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0291_geopolitical_risk_vendor_cascade"
down_revision: str | None = "0290_vendor_intel_score_confidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendor_geopolitical_exposure",
        sa.Column("cascaded_risk_id", sa.Uuid(), sa.ForeignKey("risks.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "vendor_geopolitical_exposure",
        sa.Column("last_cascaded_severity", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "vendor_geopolitical_exposure",
        sa.Column("last_cascaded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vendor_geopolitical_exposure", "last_cascaded_at")
    op.drop_column("vendor_geopolitical_exposure", "last_cascaded_severity")
    op.drop_column("vendor_geopolitical_exposure", "cascaded_risk_id")
