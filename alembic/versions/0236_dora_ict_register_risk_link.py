"""add nullable risk_id link on dora_ict_register for auto-created register findings

Revision ID: 0236_dora_risk_link
Revises: 0235_llm_observ_events
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0236_dora_risk_link"
down_revision: str | None = "0235_llm_observ_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dora_ict_register",
        sa.Column("risk_id", sa.Uuid(), sa.ForeignKey("risks.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_dora_ict_register_risk_id",
        "dora_ict_register",
        ["risk_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dora_ict_register_risk_id", table_name="dora_ict_register")
    op.drop_column("dora_ict_register", "risk_id")
