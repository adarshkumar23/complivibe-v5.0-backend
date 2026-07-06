"""add roi calculator leads table for public onboarding capture

Revision ID: 0250_roi_calculator_leads_p2b
Revises: 0249_competitor_pricing_p1b
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0250_roi_calculator_leads_p2b"
down_revision: str | None = "0249_competitor_pricing_p1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roi_calculator_leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("current_tool", sa.String(length=32), nullable=False),
        sa.Column("team_size", sa.Integer(), nullable=False),
        sa.Column("frameworks_count", sa.Integer(), nullable=False),
        sa.Column("current_annual_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("hours_saved_per_week", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("annual_saving", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("payback_period_months", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("three_year_roi_pct", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("projected_platform_annual_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("crm_status", sa.String(length=24), nullable=False, server_default="new"),
        sa.Column("lead_summary", sa.Text(), nullable=False),
        sa.Column(
            "calculation_inputs_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "current_tool IN ('vanta','drata','sprinto','scrut','onetrust','credo_ai','generic','other')",
            name="ck_roi_calculator_leads_current_tool",
        ),
        sa.CheckConstraint("team_size >= 1", name="ck_roi_calculator_leads_team_size"),
        sa.CheckConstraint("frameworks_count >= 1", name="ck_roi_calculator_leads_frameworks_count"),
        sa.CheckConstraint("current_annual_cost >= 0", name="ck_roi_calculator_leads_current_annual_cost"),
    )
    op.create_index("ix_roi_calculator_leads_org_created_at", "roi_calculator_leads", ["organization_id", "created_at"], unique=False)
    op.create_index("ix_roi_calculator_leads_current_tool", "roi_calculator_leads", ["current_tool"], unique=False)
    op.create_index("ix_roi_calculator_leads_crm_status", "roi_calculator_leads", ["crm_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_roi_calculator_leads_crm_status", table_name="roi_calculator_leads")
    op.drop_index("ix_roi_calculator_leads_current_tool", table_name="roi_calculator_leads")
    op.drop_index("ix_roi_calculator_leads_org_created_at", table_name="roi_calculator_leads")
    op.drop_table("roi_calculator_leads")
