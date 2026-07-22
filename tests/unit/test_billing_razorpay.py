from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from unittest.mock import patch

import pytest
from sqlalchemy import inspect, select

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.billing_event import BillingEvent
from app.models.organization import Organization
from app.models.subscription_plan import SubscriptionPlan
from tests.helpers.auth_org import bootstrap_org_user


def _sso_payload() -> dict:
    return {
        "provider": "okta",
        "entity_id": "https://example.okta.com/app/issuer",
        "sso_url": "https://example.okta.com/app/sso/saml",
        "slo_url": "https://example.okta.com/app/slo/saml",
        "certificate": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
        "attribute_mapping": {
            "email": "NameID",
            "first_name": "firstName",
            "last_name": "lastName",
            "role": "groups",
        },
        "jit_provisioning": True,
        "default_role": "member",
    }


@pytest.fixture(autouse=True)
def _billing_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_webhook_secret")
    monkeypatch.setenv("FRONTEND_URL", "https://app.complivibe.in")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_plan(db_session, org_id: str, *, status: str, plan: str, trial_delta_days: int | None = None):
    org = db_session.get(Organization, UUID(org_id))
    assert org is not None
    org.subscription_status = status
    org.subscription_plan = plan
    if trial_delta_days is not None:
        org.trial_ends_at = datetime.now(UTC) + timedelta(days=trial_delta_days)
    db_session.commit()


def _sign_body(body: bytes) -> str:
    secret = get_settings().RAZORPAY_WEBHOOK_SECRET.encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_billing_schema_and_plan_seed_and_features(client, db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert "subscription_plans" in tables
    assert "billing_events" in tables

    cols = {c["name"] for c in inspect(db_session.bind).get_columns("organizations")}
    assert "subscription_status" in cols
    assert "subscription_plan" in cols
    assert "trial_ends_at" in cols
    assert "razorpay_subscription_id" in cols

    plans_resp = client.get("/api/v1/billing/plans")
    assert plans_resp.status_code == 200
    plans = plans_resp.json()
    # Access model (Stage 1c-1) adds the "free" and "trial" plan rows to the
    # pre-existing starter/growth/enterprise/usage_flex, for 6 total.
    assert len(plans) == 6

    by_code = {item["plan_code"]: item for item in plans}
    assert set(by_code) == {"free", "trial", "starter", "growth", "enterprise", "usage_flex"}
    assert by_code["starter"]["features"]["max_users"] == 5
    assert by_code["starter"]["features"]["sso_enabled"] is False
    assert by_code["starter"]["plan_type"] == "fixed"
    assert by_code["growth"]["features"]["sso_enabled"] is True
    assert by_code["enterprise"]["features"]["max_users"] is None
    assert by_code["usage_flex"]["plan_type"] == "usage_based"
    assert by_code["usage_flex"]["usage_unit_price_inr"] == 12.0
    # Free = capped core creation, only privacy_basic among premium flags.
    assert by_code["free"]["features"]["record_caps"] == {"policies": 5, "controls": 5, "evidence": 5, "risks": 5}
    assert by_code["free"]["features"]["privacy_basic"] is True
    assert by_code["free"]["features"]["ai_governance_module"] is False
    # Trial = enterprise-equivalent, uncapped.
    assert by_code["trial"]["features"]["record_caps"] == {}
    assert by_code["trial"]["features"]["ai_governance_module"] is True

    # Purchasable (Razorpay-billable) plans must each have a real (even if
    # placeholder) Razorpay plan-ID mapping, monthly and annual -- otherwise
    # subscribe fails locally before ever reaching Razorpay. Free and Trial are
    # NOT Razorpay-purchasable, so they intentionally carry no plan-ID mapping.
    PURCHASABLE = {"starter", "growth", "enterprise", "usage_flex"}
    seeded_plans = db_session.execute(select(SubscriptionPlan)).scalars().all()
    assert len(seeded_plans) == 6
    for plan in seeded_plans:
        if plan.plan_code in PURCHASABLE:
            assert plan.razorpay_plan_id, f"{plan.plan_code} missing razorpay_plan_id"
            assert plan.razorpay_annual_plan_id, f"{plan.plan_code} missing razorpay_annual_plan_id"
            assert plan.razorpay_plan_id.startswith("plan_")
            assert plan.razorpay_annual_plan_id.startswith("plan_")
        else:  # free / trial
            assert plan.razorpay_plan_id is None
            assert plan.razorpay_annual_plan_id is None


def test_subscribe_never_fails_locally_for_missing_plan_id_mapping(client, db_session):
    """G9 item 11: subscribe must reach the Razorpay call for every seeded plan code
    instead of 422'ing on a missing local plan-ID mapping."""
    org = bootstrap_org_user(client, email_prefix="billing-plan-mapping")

    for plan_code, cycle in [("starter", "monthly"), ("growth", "annual"), ("enterprise", "monthly"), ("usage_flex", "annual")]:
        response = client.post(
            "/api/v1/billing/subscribe",
            headers=org["org_headers"],
            json={"plan_code": plan_code, "billing_cycle": cycle},
        )
        # Credentials are disabled/placeholder in this environment, so the real
        # Razorpay call fails upstream (502) -- the important assertion is that it's
        # NOT the local 422 "Razorpay plan ID not configured" error.
        assert response.status_code != 422, response.text
        assert "not configured" not in response.text


def test_registration_lands_on_free_and_expiry_gate(client, db_session):
    # Stage 1c-1: a newly self-registered org lands on the Free plan (active,
    # no trial) -- NOT an auto-started trial. A trial is only entered by
    # redeeming a trial code (Stage 1c-2).
    org = bootstrap_org_user(client, email_prefix="billing-free")

    status_resp = client.get("/api/v1/billing/status", headers=org["org_headers"])
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["subscription_status"] == "active"
    assert data["plan"] == "free"
    assert data["is_trial"] is False
    assert data["trial_ends_at"] is None

    # The trial-expiry gate itself is unchanged: an org explicitly in an expired
    # trial is blocked with 402 trial_expired (lazy downgrade lands in 1c-5).
    _set_plan(db_session, org["organization_id"], status="trial", plan="starter", trial_delta_days=-1)
    expired = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sso_payload())
    assert expired.status_code == 402
    assert expired.json()["detail"]["error"] == "trial_expired"


def test_billing_status_requires_membership_in_requested_org(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="billing-member-a")
    org_b = bootstrap_org_user(client, email_prefix="billing-member-b")
    mixed_headers = {**org_a["headers"], "X-Organization-ID": org_b["organization_id"]}

    response = client.get("/api/v1/billing/status", headers=mixed_headers)
    assert response.status_code == 403


def test_subscribe_and_invoices_mocked(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-sub")

    client.get("/api/v1/billing/plans")
    starter = db_session.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == "starter")).scalar_one()
    starter.razorpay_plan_id = "plan_starter_monthly"
    db_session.flush()

    with (
        patch("app.platform.services.razorpay_service.RazorpayService.create_customer", return_value="cust_123"),
        patch(
            "app.platform.services.razorpay_service.RazorpayService.create_subscription",
            return_value={"id": "sub_123", "short_url": "https://rzp.io/pay/sub_123"},
        ),
    ):
        resp = client.post(
            "/api/v1/billing/subscribe",
            headers=org["org_headers"],
            json={"plan_code": "starter", "billing_cycle": "monthly"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["payment_url"].startswith("https://")
    assert body["subscription_id"] == "sub_123"

    org_row = db_session.get(Organization, UUID(org["organization_id"]))
    assert org_row is not None
    assert org_row.razorpay_subscription_id == "sub_123"

    with patch(
        "app.platform.services.razorpay_service.RazorpayService.get_invoices",
        return_value=[{"id": "inv_1", "amount": 499900, "currency": "INR", "status": "paid", "billing_start": 1710000000, "short_url": "https://rzp.io/i/inv_1"}],
    ):
        inv = client.get("/api/v1/billing/invoices", headers=org["org_headers"])
    assert inv.status_code == 200
    assert inv.json()[0]["id"] == "inv_1"


def test_webhook_signature_and_status_transitions_and_idempotency(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-webhook")
    org_row = db_session.get(Organization, UUID(org["organization_id"]))
    assert org_row is not None
    org_row.razorpay_subscription_id = "sub_webhook"
    db_session.flush()

    payload = {
        "event": "subscription.activated",
        "payload": {"subscription": {"entity": {"id": "sub_webhook", "plan_id": "plan_unknown"}}},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign_body(body)

    valid = client.post(
        "/api/webhook/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_1",
        },
    )
    assert valid.status_code == 200
    assert valid.json()["status"] == "processed"

    db_session.refresh(org_row)
    assert org_row.subscription_status == "active"

    duplicate = client.post(
        "/api/webhook/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_1",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "already_processed"

    events = db_session.execute(select(BillingEvent).where(BillingEvent.razorpay_event_id == "evt_1")).scalars().all()
    assert len(events) == 1

    bad_sig = client.post(
        "/api/webhook/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "bad",
            "X-Razorpay-Event-Id": "evt_bad",
        },
    )
    assert bad_sig.status_code == 400

    halted_payload = {"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": "sub_webhook"}}}}
    halted_body = json.dumps(halted_payload).encode("utf-8")
    halted = client.post(
        "/api/webhook/razorpay",
        content=halted_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": _sign_body(halted_body),
            "X-Razorpay-Event-Id": "evt_2",
        },
    )
    assert halted.status_code == 200
    db_session.refresh(org_row)
    assert org_row.subscription_status == "past_due"

    cancelled_payload = {"event": "subscription.cancelled", "payload": {"subscription": {"entity": {"id": "sub_webhook"}}}}
    cancelled_body = json.dumps(cancelled_payload).encode("utf-8")
    cancelled = client.post(
        "/api/webhook/razorpay",
        content=cancelled_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": _sign_body(cancelled_body),
            "X-Razorpay-Event-Id": "evt_3",
        },
    )
    assert cancelled.status_code == 200
    db_session.refresh(org_row)
    assert org_row.subscription_status == "cancelled"


def test_feature_gating_starter_vs_growth_and_subscription_required(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-gate")

    _set_plan(db_session, org["organization_id"], status="active", plan="starter")
    starter_blocked = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sso_payload())
    assert starter_blocked.status_code == 403
    assert starter_blocked.json()["detail"]["error"] == "feature_not_in_plan"
    assert "upgrade_url" in starter_blocked.json()["detail"]

    _set_plan(db_session, org["organization_id"], status="active", plan="growth")
    growth_allowed = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sso_payload())
    assert growth_allowed.status_code == 201

    _set_plan(db_session, org["organization_id"], status="past_due", plan="growth")
    blocked = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sso_payload())
    assert blocked.status_code == 402
    assert blocked.json()["detail"]["error"] == "subscription_required"


def test_audit_logging_for_billing_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="billing-audit")
    org_row = db_session.get(Organization, UUID(org["organization_id"]))
    assert org_row is not None
    org_row.razorpay_subscription_id = "sub_audit"
    db_session.flush()

    def _post(event: str, event_id: str):
        payload = {"event": event, "payload": {"subscription": {"entity": {"id": "sub_audit"}}}}
        body = json.dumps(payload).encode("utf-8")
        return client.post(
            "/api/webhook/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": _sign_body(body),
                "X-Razorpay-Event-Id": event_id,
            },
        )

    assert _post("subscription.activated", "evt_a").status_code == 200
    assert _post("subscription.charged", "evt_b").status_code == 200
    assert _post("subscription.cancelled", "evt_c").status_code == 200

    actions = set(
        db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == UUID(org["organization_id"]),
                AuditLog.action.in_(
                    [
                        "billing.subscription_activated",
                        "billing.subscription_cancelled",
                        "billing.payment_charged",
                    ]
                ),
            )
        ).scalars()
    )
    assert "billing.subscription_activated" in actions
    assert "billing.subscription_cancelled" in actions
    assert "billing.payment_charged" in actions
