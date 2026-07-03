"""billing razorpay integration

Revision ID: 0173_billing_razorpay_integration
Revises: 0172_ai_depth_schema
Create Date: 2026-06-29 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0173_billing_razorpay_integration"
down_revision: str | None = "0172_ai_depth_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORG_COLUMNS: list[tuple[str, sa.Column]] = [
    (
        "subscription_status",
        sa.Column("subscription_status", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'trial'")),
    ),
    (
        "subscription_plan",
        sa.Column("subscription_plan", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'starter'")),
    ),
    ("trial_ends_at", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True)),
    ("subscription_ends_at", sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True)),
    ("razorpay_customer_id", sa.Column("razorpay_customer_id", sa.VARCHAR(length=100), nullable=True)),
    ("razorpay_subscription_id", sa.Column("razorpay_subscription_id", sa.VARCHAR(length=100), nullable=True)),
]


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "organizations"):
        for column_name, column in ORG_COLUMNS:
            if not _has_column(inspector, "organizations", column_name):
                op.add_column("organizations", column)

        inspector = sa.inspect(bind)
        if not _has_constraint(inspector, "organizations", "ck_organizations_subscription_status"):
            op.create_check_constraint(
                "ck_organizations_subscription_status",
                "organizations",
                "subscription_status IN ('trial', 'active', 'past_due', 'cancelled', 'paused', 'expired')",
            )

        inspector = sa.inspect(bind)
        if not _has_constraint(inspector, "organizations", "ck_organizations_subscription_plan"):
            op.create_check_constraint(
                "ck_organizations_subscription_plan",
                "organizations",
                "subscription_plan IN ('trial', 'starter', 'growth', 'enterprise')",
            )

        op.execute(
            """
            UPDATE organizations
            SET trial_ends_at = NOW() + INTERVAL '14 days',
                subscription_status = 'trial'
            WHERE trial_ends_at IS NULL
            """
        )

        inspector = sa.inspect(bind)
        if not _has_index(inspector, "organizations", "ix_organizations_subscription_status"):
            op.create_index(
                "ix_organizations_subscription_status",
                "organizations",
                ["subscription_status"],
                unique=False,
            )

        inspector = sa.inspect(bind)
        if not _has_index(inspector, "organizations", "ix_organizations_razorpay_sub_id"):
            op.create_index(
                "ix_organizations_razorpay_sub_id",
                "organizations",
                ["razorpay_subscription_id"],
                unique=False,
                postgresql_where=sa.text("razorpay_subscription_id IS NOT NULL"),
            )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "subscription_plans"):
        op.create_table(
            "subscription_plans",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("plan_code", sa.VARCHAR(length=20), nullable=False, unique=True),
            sa.Column("display_name", sa.VARCHAR(length=100), nullable=False),
            sa.Column("price_inr_monthly", sa.Integer(), nullable=False),
            sa.Column("price_inr_annual", sa.Integer(), nullable=False),
            sa.Column("razorpay_plan_id", sa.VARCHAR(length=100), nullable=True),
            sa.Column("razorpay_annual_plan_id", sa.VARCHAR(length=100), nullable=True),
            sa.Column("max_users", sa.Integer(), nullable=True),
            sa.Column("max_frameworks", sa.Integer(), nullable=True),
            sa.Column("max_ai_systems", sa.Integer(), nullable=True),
            sa.Column("max_dsr_per_month", sa.Integer(), nullable=True),
            sa.Column("features", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO subscription_plans (
                plan_code, display_name, price_inr_monthly, price_inr_annual,
                max_users, max_frameworks, max_ai_systems, max_dsr_per_month,
                features, is_active
            ) VALUES (
                :plan_code, :display_name, :price_inr_monthly, :price_inr_annual,
                :max_users, :max_frameworks, :max_ai_systems, :max_dsr_per_month,
                CAST(:features AS jsonb), true
            )
            ON CONFLICT(plan_code) DO NOTHING
            """
        ),
        {
            "plan_code": "starter",
            "display_name": "Starter",
            "price_inr_monthly": 499900,
            "price_inr_annual": 4799000,
            "max_users": 5,
            "max_frameworks": 3,
            "max_ai_systems": 2,
            "max_dsr_per_month": 10,
            "features": '{"max_users":5,"max_frameworks":3,"max_ai_systems":2,"max_dsr_per_month":10,"sso_enabled":false,"scim_enabled":false,"siem_export":false,"api_access":true,"audit_log_days":90,"support":"email"}',
        },
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO subscription_plans (
                plan_code, display_name, price_inr_monthly, price_inr_annual,
                max_users, max_frameworks, max_ai_systems, max_dsr_per_month,
                features, is_active
            ) VALUES (
                :plan_code, :display_name, :price_inr_monthly, :price_inr_annual,
                :max_users, :max_frameworks, :max_ai_systems, :max_dsr_per_month,
                CAST(:features AS jsonb), true
            )
            ON CONFLICT(plan_code) DO NOTHING
            """
        ),
        {
            "plan_code": "growth",
            "display_name": "Growth",
            "price_inr_monthly": 1499900,
            "price_inr_annual": 14399000,
            "max_users": 25,
            "max_frameworks": 10,
            "max_ai_systems": 10,
            "max_dsr_per_month": 100,
            "features": '{"max_users":25,"max_frameworks":10,"max_ai_systems":10,"max_dsr_per_month":100,"sso_enabled":true,"scim_enabled":false,"siem_export":true,"api_access":true,"audit_log_days":365,"support":"priority_email"}',
        },
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO subscription_plans (
                plan_code, display_name, price_inr_monthly, price_inr_annual,
                max_users, max_frameworks, max_ai_systems, max_dsr_per_month,
                features, is_active
            ) VALUES (
                :plan_code, :display_name, :price_inr_monthly, :price_inr_annual,
                :max_users, :max_frameworks, :max_ai_systems, :max_dsr_per_month,
                CAST(:features AS jsonb), true
            )
            ON CONFLICT(plan_code) DO NOTHING
            """
        ),
        {
            "plan_code": "enterprise",
            "display_name": "Enterprise",
            "price_inr_monthly": 4999900,
            "price_inr_annual": 47999000,
            "max_users": None,
            "max_frameworks": None,
            "max_ai_systems": None,
            "max_dsr_per_month": None,
            "features": '{"max_users":null,"max_frameworks":null,"max_ai_systems":null,"max_dsr_per_month":null,"sso_enabled":true,"scim_enabled":true,"siem_export":true,"api_access":true,"audit_log_days":730,"support":"dedicated_csm"}',
        },
    )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "billing_events"):
        op.create_table(
            "billing_events",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.VARCHAR(length=50), nullable=False),
            sa.Column("razorpay_event_id", sa.VARCHAR(length=100), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("razorpay_event_id", name="uq_billing_events_razorpay_event_id"),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "billing_events", "ix_billing_events_org_event"):
        op.create_index("ix_billing_events_org_event", "billing_events", ["organization_id", "event_type"], unique=False)
    if not _has_index(inspector, "billing_events", "ix_billing_events_processed_created"):
        op.create_index("ix_billing_events_processed_created", "billing_events", ["processed", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "billing_events"):
        if _has_index(inspector, "billing_events", "ix_billing_events_processed_created"):
            op.drop_index("ix_billing_events_processed_created", table_name="billing_events")
        if _has_index(inspector, "billing_events", "ix_billing_events_org_event"):
            op.drop_index("ix_billing_events_org_event", table_name="billing_events")
        op.drop_table("billing_events")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "subscription_plans"):
        op.drop_table("subscription_plans")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "organizations"):
        if _has_index(inspector, "organizations", "ix_organizations_razorpay_sub_id"):
            op.drop_index("ix_organizations_razorpay_sub_id", table_name="organizations")
        if _has_index(inspector, "organizations", "ix_organizations_subscription_status"):
            op.drop_index("ix_organizations_subscription_status", table_name="organizations")

        if _has_constraint(inspector, "organizations", "ck_organizations_subscription_plan"):
            op.drop_constraint("ck_organizations_subscription_plan", "organizations", type_="check")
        if _has_constraint(inspector, "organizations", "ck_organizations_subscription_status"):
            op.drop_constraint("ck_organizations_subscription_status", "organizations", type_="check")

        inspector = sa.inspect(bind)
        for column_name, _ in reversed(ORG_COLUMNS):
            if _has_column(inspector, "organizations", column_name):
                op.drop_column("organizations", column_name)
            inspector = sa.inspect(bind)
