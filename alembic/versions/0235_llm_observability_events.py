"""add llm_observability_events table for LLM tracing, hallucination, cost, and RAG monitoring

Revision ID: 0235_llm_observ_events
Revises: 0234_carbon_scope3
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0235_llm_observ_events"
down_revision: str | None = "0234_carbon_scope3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_observability_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("ai_system_id", sa.Uuid(), sa.ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source_tool", sa.String(length=100), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flag_reason", sa.String(length=255), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('trace', 'hallucination_check', 'cost_reading', 'rag_evaluation')",
            name="ck_llm_observability_events_event_type",
        ),
    )
    op.create_index(
        "ix_llm_observability_events_org_system",
        "llm_observability_events",
        ["organization_id", "ai_system_id"],
    )
    op.create_index(
        "ix_llm_observability_events_org_type",
        "llm_observability_events",
        ["organization_id", "event_type"],
    )
    op.create_index(
        "ix_llm_observability_events_org_flagged",
        "llm_observability_events",
        ["organization_id", "is_flagged"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_observability_events_org_flagged", table_name="llm_observability_events")
    op.drop_index("ix_llm_observability_events_org_type", table_name="llm_observability_events")
    op.drop_index("ix_llm_observability_events_org_system", table_name="llm_observability_events")
    op.drop_table("llm_observability_events")
