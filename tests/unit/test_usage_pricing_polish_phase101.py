from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.organization import Organization
from app.models.subscription_plan import SubscriptionPlan
from app.models.usage_billing_snapshot import UsageBillingSnapshot
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _billing_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_webhook_secret")
    monkeypatch.setenv("FRONTEND_URL", "https://app.complivibe.in")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_plan(db_session, org_id: str, *, status: str, plan: str):
    org = db_session.get(Organization, UUID(org_id))
    assert org is not None
    org.subscription_status = status
    org.subscription_plan = plan
    db_session.commit()
    return org


def _activate_usage_flex_plan(db_session, organization_id: str, *, with_subscription_id: bool = True) -> Organization:
    from app.platform.services.billing_service import BillingService

    BillingService(db_session).ensure_default_plans()
    org = db_session.get(Organization, UUID(organization_id))
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = "usage_flex"
    if with_subscription_id:
        org.razorpay_subscription_id = "sub_usage_test"
    db_session.flush()
    return org


def test_usage_dashboard_flags_fixed_plan_and_zero_usage(client, db_session):
    from app.platform.services.billing_service import BillingService

    org = bootstrap_org_user(client, email_prefix="usage-fixed-plan")
    BillingService(db_session).ensure_default_plans()
    _set_plan(db_session, org["organization_id"], status="active", plan="starter")

    resp = client.get("/api/v1/billing/usage/dashboard", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_usage_based_plan"] is False
    assert "estimated_cost_not_billable_fixed_plan" in body["context_flags"]
    assert body["cost_trend"] == "no_prior_period_data"


def test_usage_dashboard_cost_trend_vs_prior_period(client, db_session):
    org = bootstrap_org_user(client, email_prefix="usage-trend")
    org_row = _activate_usage_flex_plan(db_session, org["organization_id"], with_subscription_id=False)

    plan = db_session.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == "usage_flex")).scalar_one()

    today = datetime.now(UTC).date()
    if today.month == 1:
        prev_start = date(today.year - 1, 12, 1)
        prev_end = date(today.year - 1, 12, 31)
    else:
        prev_start = date(today.year, today.month - 1, 1)
        next_month_first = date(today.year, today.month, 1)
        prev_end = date.fromordinal(next_month_first.toordinal() - 1)

    db_session.add(
        UsageBillingSnapshot(
            organization_id=org_row.id,
            subscription_plan_id=plan.id,
            period_start=prev_start,
            period_end=prev_end,
            active_frameworks_count=1,
            active_users_count=1,
            api_calls_count=0,
            billable_units=Decimal("1.00"),
            unit_price_inr=Decimal("12.00"),
            current_estimated_cost_inr=Decimal("12.00"),
            projected_month_end_cost_inr=Decimal("12.00"),
            synced_to_processor=False,
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/billing/usage/dashboard", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous_period_cost_inr"] == 12.0
    assert body["cost_trend"] in {"increasing", "decreasing", "flat"}

    snapshot = db_session.execute(
        select(UsageBillingSnapshot)
        .where(UsageBillingSnapshot.organization_id == org_row.id, UsageBillingSnapshot.period_start == today.replace(day=1))
        .order_by(UsageBillingSnapshot.created_at.desc())
    ).scalar_one_or_none()
    assert snapshot is not None


def test_usage_sync_still_blocks_on_spend_cap_and_dashboard_shows_soft_warning(client, db_session):
    org = bootstrap_org_user(client, email_prefix="usage-cap-block-101")
    _activate_usage_flex_plan(db_session, org["organization_id"], with_subscription_id=True)

    update = client.post(
        "/api/v1/billing/usage/spend-cap",
        headers=org["org_headers"],
        json={"usage_spend_cap_enabled": True, "usage_spend_cap_inr": 1},
    )
    assert update.status_code == 200

    blocked = client.post("/api/v1/billing/usage/sync", headers=org["org_headers"])
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked_spend_cap"

    dash = client.get("/api/v1/billing/usage/dashboard", headers=org["org_headers"])
    assert dash.status_code == 200
    assert dash.json()["is_spend_cap_breached"] is True
    assert dash.json()["is_usage_based_plan"] is True
