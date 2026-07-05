"""t13 vendor nth party risk flags

Revision ID: 0228_t13_supply_chain_flags
Revises: 0227_training_analytics
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0228_t13_supply_chain_flags"
down_revision: str | None = "0227_training_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("nth_party_risk_flag", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("vendors", sa.Column("nth_party_risk_severity", sa.String(length=32), nullable=True))
    op.add_column("vendors", sa.Column("nth_party_risk_signal_type", sa.String(length=80), nullable=True))
    op.add_column("vendors", sa.Column("nth_party_risk_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_vendors_org_nth_party_flag", "vendors", ["organization_id", "nth_party_risk_flag"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendors_org_nth_party_flag", table_name="vendors")
    op.drop_column("vendors", "nth_party_risk_updated_at")
    op.drop_column("vendors", "nth_party_risk_signal_type")
    op.drop_column("vendors", "nth_party_risk_severity")
    op.drop_column("vendors", "nth_party_risk_flag")
