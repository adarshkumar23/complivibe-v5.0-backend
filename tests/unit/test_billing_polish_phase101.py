from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.organization import Organization
from app.models.subscription_plan import SubscriptionPlan
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


def _set_plan(db_session, org_id: str, *, status: str, plan: str, trial_delta_days: int | None = None,
              subscription_ends_delta_days: int | None = None, razorpay_subscription_id: str | None = None):
    org = db_session.get(Organization, UUID(org_id))
    assert org is not None
    org.subscription_status = status
    org.subscription_plan = plan
    if trial_delta_days is not None:
        org.trial_ends_at = datetime.now(UTC) + timedelta(days=trial_delta_days)
    if subscription_ends_delta_days is not None:
        org.subscription_ends_at = datetime.now(UTC) + timedelta(days=subscription_ends_delta_days)
    if razorpay_subscription_id is not None:
        org.razorpay_subscription_id = razorpay_subscription_id
    db_session.commit()
    return org


def test_billing_status_flags_trial_ending_soon(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-trial-soon")
    _set_plan(db_session, org["organization_id"], status="trial", plan="starter", trial_delta_days=2)

    resp = client.get("/api/v1/billing/status", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "trial_ending_soon" in body["context_flags"]


def test_billing_status_flags_pending_cancellation_and_missing_provider_link(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-pending-cancel")
    _set_plan(
        db_session,
        org["organization_id"],
        status="active",
        plan="growth",
        subscription_ends_delta_days=10,
    )

    resp = client.get("/api/v1/billing/status", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "pending_cancellation_at_period_end" in body["context_flags"]
    assert "missing_payment_provider_link" in body["context_flags"]
    assert body["renewal_days_remaining"] is not None


def test_billing_status_flags_plan_not_found(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-plan-missing")
    org_row = _set_plan(db_session, org["organization_id"], status="active", plan="ghost_plan")

    resp = client.get("/api/v1/billing/status", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "plan_not_found" in body["context_flags"]
    assert body["features"] == {}
    assert org_row.subscription_plan == "ghost_plan"


def test_cancel_subscription_rejects_duplicate_cancellation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-double-cancel")
    _set_plan(
        db_session,
        org["organization_id"],
        status="active",
        plan="starter",
        razorpay_subscription_id="sub_dup_cancel",
    )

    with patch("app.platform.services.razorpay_service.RazorpayService.cancel_subscription", return_value={}):
        first = client.post(
            "/api/v1/billing/cancel",
            headers=org["org_headers"],
            json={"cancel_at_cycle_end": False},
        )
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/billing/cancel",
        headers=org["org_headers"],
        json={"cancel_at_cycle_end": False},
    )
    assert second.status_code == 409, second.text


def test_subscribe_rejects_duplicate_active_same_plan(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-dup-sub")
    _set_plan(
        db_session,
        org["organization_id"],
        status="active",
        plan="starter",
        razorpay_subscription_id="sub_already_active",
    )

    resp = client.post(
        "/api/v1/billing/subscribe",
        headers=org["org_headers"],
        json={"plan_code": "starter", "billing_cycle": "monthly"},
    )
    assert resp.status_code == 409, resp.text


def test_subscribe_surfaces_bad_gateway_on_processor_failure(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-processor-fail")

    client.get("/api/v1/billing/plans")
    starter = db_session.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == "starter")).scalar_one()
    starter.razorpay_plan_id = "plan_starter_monthly"
    db_session.flush()

    with patch(
        "app.platform.services.razorpay_service.RazorpayService.create_customer",
        side_effect=RuntimeError("razorpay unreachable"),
    ):
        resp = client.post(
            "/api/v1/billing/subscribe",
            headers=org["org_headers"],
            json={"plan_code": "starter", "billing_cycle": "monthly"},
        )
    assert resp.status_code == 502, resp.text
