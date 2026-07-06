from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.usage_billing_snapshot import UsageBillingSnapshot
from tests.helpers.auth_org import bootstrap_org_user


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


def test_usage_billing_schema_and_dashboard(client, db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert "usage_billing_snapshots" in tables

    org = bootstrap_org_user(client, email_prefix="usage-dash")
    org_row = _activate_usage_flex_plan(db_session, org["organization_id"], with_subscription_id=False)

    resp = client.get("/api/v1/billing/usage/dashboard", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["active_frameworks_count"] >= 0
    assert payload["active_users_count"] >= 1
    assert payload["billable_units"] >= 0
    assert payload["projected_month_end_cost_inr"] >= 0
    assert payload["synced_to_processor"] is False
    assert payload["usage_spend_cap_enabled"] is False

    snapshot = db_session.execute(
        select(UsageBillingSnapshot)
        .where(UsageBillingSnapshot.organization_id == org_row.id)
        .order_by(UsageBillingSnapshot.created_at.desc())
    ).scalar_one_or_none()
    assert snapshot is not None


def test_usage_spend_cap_and_sync_to_processor(client, db_session):
    org = bootstrap_org_user(client, email_prefix="usage-sync")
    _activate_usage_flex_plan(db_session, org["organization_id"], with_subscription_id=True)

    cap_resp = client.post(
        "/api/v1/billing/usage/spend-cap",
        headers=org["org_headers"],
        json={"usage_spend_cap_enabled": True, "usage_spend_cap_inr": 250000},
    )
    assert cap_resp.status_code == 200, cap_resp.text
    assert cap_resp.json()["usage_spend_cap_enabled"] is True

    with patch(
        "app.platform.services.razorpay_service.RazorpayService.update_subscription_quantity",
        return_value={"id": "sub_usage_test"},
    ):
        sync = client.post("/api/v1/billing/usage/sync", headers=org["org_headers"])
    assert sync.status_code == 200, sync.text
    sync_payload = sync.json()
    assert sync_payload["status"] == "synced"
    assert sync_payload["processor_reference"] == "sub_usage_test"

    latest = db_session.execute(
        select(UsageBillingSnapshot)
        .where(UsageBillingSnapshot.organization_id == UUID(org["organization_id"]))
        .order_by(UsageBillingSnapshot.created_at.desc())
    ).scalar_one()
    assert latest.synced_to_processor is True
    assert latest.processor_reference == "sub_usage_test"

    actions = set(
        db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == UUID(org["organization_id"]),
                AuditLog.action.in_(
                    [
                        "billing.usage_spend_cap_updated",
                        "billing.usage_synced_to_processor",
                    ]
                ),
            )
        ).scalars()
    )
    assert "billing.usage_spend_cap_updated" in actions
    assert "billing.usage_synced_to_processor" in actions


def test_usage_sync_blocks_when_spend_cap_breached(client, db_session):
    org = bootstrap_org_user(client, email_prefix="usage-cap-block")
    _activate_usage_flex_plan(db_session, org["organization_id"], with_subscription_id=True)

    update = client.post(
        "/api/v1/billing/usage/spend-cap",
        headers=org["org_headers"],
        json={"usage_spend_cap_enabled": True, "usage_spend_cap_inr": 1},
    )
    assert update.status_code == 200

    blocked = client.post("/api/v1/billing/usage/sync", headers=org["org_headers"])
    assert blocked.status_code == 200
    body = blocked.json()
    assert body["status"] == "blocked_spend_cap"

    row = db_session.execute(
        select(UsageBillingSnapshot)
        .where(UsageBillingSnapshot.organization_id == UUID(org["organization_id"]))
        .order_by(UsageBillingSnapshot.created_at.desc())
    ).scalar_one()
    assert row.is_spend_cap_breached is True
    assert row.synced_to_processor is False
