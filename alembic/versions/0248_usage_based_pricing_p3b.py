"""add usage based pricing schema and usage snapshots

Revision ID: 0248_usage_based_pricing_p3b
Revises: 0247_roi_calculator_leads_p2b
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0248_usage_based_pricing_p3b"
down_revision: str | None = "0247_roi_calculator_leads_p2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("plan_type", sa.String(length=24), nullable=False, server_default="fixed"),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("usage_unit_price_inr", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "subscription_plans",
        sa.Column(
            "usage_weights_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_check_constraint(
        "ck_subscription_plans_plan_type",
        "subscription_plans",
        "plan_type IN ('fixed','usage_based')",
    )
    op.create_index("ix_subscription_plans_plan_type", "subscription_plans", ["plan_type"], unique=False)

    op.add_column(
        "organizations",
        sa.Column("usage_spend_cap_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "organizations",
        sa.Column("usage_spend_cap_inr", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.drop_constraint("ck_organizations_subscription_plan", "organizations", type_="check")
    op.create_check_constraint(
        "ck_organizations_subscription_plan",
        "organizations",
        "subscription_plan IN ('trial','starter','growth','enterprise','usage_flex')",
    )

    op.create_table(
        "usage_billing_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_plan_id", sa.Uuid(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("active_frameworks_count", sa.Integer(), nullable=False),
        sa.Column("active_users_count", sa.Integer(), nullable=False),
        sa.Column("api_calls_count", sa.Integer(), nullable=False),
        sa.Column("billable_units", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("unit_price_inr", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("current_estimated_cost_inr", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("projected_month_end_cost_inr", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("spend_cap_inr", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("is_spend_cap_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("synced_to_processor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processor_reference", sa.String(length=128), nullable=True),
        sa.Column(
            "source_inputs_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_plan_id"], ["subscription_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("period_end >= period_start", name="ck_usage_billing_snapshots_period_range"),
        sa.CheckConstraint("active_frameworks_count >= 0", name="ck_usage_billing_snapshots_frameworks"),
        sa.CheckConstraint("active_users_count >= 0", name="ck_usage_billing_snapshots_users"),
        sa.CheckConstraint("api_calls_count >= 0", name="ck_usage_billing_snapshots_api_calls"),
        sa.CheckConstraint("billable_units >= 0", name="ck_usage_billing_snapshots_billable_units"),
    )
    op.create_index(
        "ix_usage_billing_snapshots_org_period_start",
        "usage_billing_snapshots",
        ["organization_id", "period_start"],
        unique=False,
    )
    op.create_index(
        "ix_usage_billing_snapshots_org_created_at",
        "usage_billing_snapshots",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_billing_snapshots_synced",
        "usage_billing_snapshots",
        ["organization_id", "synced_to_processor"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_billing_snapshots_synced", table_name="usage_billing_snapshots")
    op.drop_index("ix_usage_billing_snapshots_org_created_at", table_name="usage_billing_snapshots")
    op.drop_index("ix_usage_billing_snapshots_org_period_start", table_name="usage_billing_snapshots")
    op.drop_table("usage_billing_snapshots")

    op.drop_constraint("ck_organizations_subscription_plan", "organizations", type_="check")
    op.create_check_constraint(
        "ck_organizations_subscription_plan",
        "organizations",
        "subscription_plan IN ('trial','starter','growth','enterprise')",
    )
    op.drop_column("organizations", "usage_spend_cap_inr")
    op.drop_column("organizations", "usage_spend_cap_enabled")

    op.drop_index("ix_subscription_plans_plan_type", table_name="subscription_plans")
    op.drop_constraint("ck_subscription_plans_plan_type", "subscription_plans", type_="check")
    op.drop_column("subscription_plans", "usage_weights_json")
    op.drop_column("subscription_plans", "usage_unit_price_inr")
    op.drop_column("subscription_plans", "plan_type")
