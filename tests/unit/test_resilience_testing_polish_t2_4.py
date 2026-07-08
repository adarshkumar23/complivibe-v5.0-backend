from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.models.dora_ict_register import DORAICTRegister
from app.models.resilience_testing import ResilienceTest
from tests.helpers.auth_org import bootstrap_org_user


def _create_test(client, headers, **overrides):
    payload = {
        "test_type": "tabletop",
        "scope": "Core payment processing systems",
        "scheduled_date": date.today().isoformat(),
        "owner_team": "Security",
    }
    payload.update(overrides)
    return client.post("/api/v1/resilience-tests", headers=headers, json=payload)


def _create_critical_vendor(client, headers, user_id, **overrides):
    payload = {
        "counterparty_name": "CloudCore Hosting Ltd",
        "service_description": "Primary core banking hosting provider",
        "is_critical_function": True,
        "sub_outsourcing_used": False,
        "exit_strategy_documented": True,
        "owner_id": user_id,
        "status": "active",
    }
    payload.update(overrides)
    return client.post("/api/v1/compliance/dora/ict-register", headers=headers, json=payload)


def test_completed_test_referencing_vendor_without_exit_strategy_is_flagged(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-noexit")
    headers = org_user["org_headers"]
    user_id = org_user["user_id"]

    vendor_resp = _create_critical_vendor(client, headers, user_id, exit_strategy_documented=False)
    assert vendor_resp.status_code == 201, vendor_resp.text

    test_resp = _create_test(client, headers, scope="Failover test for CloudCore Hosting Ltd primary DC")
    assert test_resp.status_code == 201, test_resp.text
    test_id = test_resp.json()["id"]

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={"results_json": {"summary": "Failover succeeded", "findings": []}},
    )
    assert complete_resp.status_code == 200, complete_resp.text
    flags = complete_resp.json()["test"]["context_flags"]
    assert any("referenced_vendor_lacks_documented_exit_strategy" in f for f in flags)


def test_completed_test_referencing_inactive_vendor_is_flagged(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-inactive-vendor")
    headers = org_user["org_headers"]
    user_id = org_user["user_id"]

    vendor_resp = _create_critical_vendor(
        client, headers, user_id, counterparty_name="LegacyPay Processor", status="under_review"
    )
    assert vendor_resp.status_code == 201, vendor_resp.text

    test_resp = _create_test(client, headers, scope="Resilience drill covering LegacyPay Processor gateway")
    assert test_resp.status_code == 201, test_resp.text
    test_id = test_resp.json()["id"]

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={"results_json": {"summary": "OK", "findings": []}},
    )
    assert complete_resp.status_code == 200, complete_resp.text
    flags = complete_resp.json()["test"]["context_flags"]
    assert any("referenced_vendor_register_entry_not_active" in f for f in flags)


def test_test_predates_vendor_register_update_is_flagged(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-stale-vendor")
    headers = org_user["org_headers"]
    user_id = org_user["user_id"]

    vendor_resp = _create_critical_vendor(client, headers, user_id, counterparty_name="NorthBridge Data Center")
    assert vendor_resp.status_code == 201, vendor_resp.text
    vendor_id = vendor_resp.json()["id"]

    test_resp = _create_test(client, headers, scope="DR simulation for NorthBridge Data Center")
    assert test_resp.status_code == 201, test_resp.text
    test_id = test_resp.json()["id"]

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={"results_json": {"summary": "OK", "findings": []}},
    )
    assert complete_resp.status_code == 200, complete_resp.text

    # Backdate the test's completion so the vendor's next update clearly postdates it.
    db_test = db_session.get(ResilienceTest, uuid.UUID(test_id))
    db_test.completed_date = date.today() - timedelta(days=5)
    db_session.commit()

    # Mutate the vendor register entry (e.g. an SLA/contract detail change) --
    # onupdate bumps updated_at to "now", after the backdated completion.
    patch_resp = client.patch(
        f"/api/v1/compliance/dora/ict-register/{vendor_id}",
        headers=headers,
        json={"service_description": "Primary core banking hosting provider (SLA renegotiated)"},
    )
    assert patch_resp.status_code == 200, patch_resp.text

    detail = client.get(f"/api/v1/resilience-tests/{test_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    flags = detail.json()["context_flags"]
    assert any("vendor_register_changed_since_test_completion" in f for f in flags)


def test_test_scope_not_referencing_any_vendor_has_no_flags(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-novendor")
    headers = org_user["org_headers"]
    user_id = org_user["user_id"]

    vendor_resp = _create_critical_vendor(client, headers, user_id)
    assert vendor_resp.status_code == 201, vendor_resp.text

    test_resp = _create_test(client, headers, scope="Internal tabletop unrelated to any third party")
    assert test_resp.status_code == 201, test_resp.text
    test_id = test_resp.json()["id"]

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={"results_json": {"summary": "OK", "findings": []}},
    )
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["test"]["context_flags"] == []


def test_list_endpoint_surfaces_context_flags(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-list-flags")
    headers = org_user["org_headers"]
    user_id = org_user["user_id"]

    vendor_resp = _create_critical_vendor(client, headers, user_id, exit_strategy_documented=False)
    assert vendor_resp.status_code == 201, vendor_resp.text

    test_resp = _create_test(client, headers, scope="Annual review covering CloudCore Hosting Ltd")
    assert test_resp.status_code == 201, test_resp.text
    test_id = test_resp.json()["id"]
    client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={"results_json": {"summary": "OK", "findings": []}},
    )

    list_resp = client.get("/api/v1/resilience-tests", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    matched = next(t for t in list_resp.json() if t["id"] == test_id)
    assert any("referenced_vendor_lacks_documented_exit_strategy" in f for f in matched["context_flags"])
