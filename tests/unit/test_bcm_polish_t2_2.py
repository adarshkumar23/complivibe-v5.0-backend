from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user


def _create_process(client, headers, **overrides):
    payload = {
        "name": "Payroll Processing",
        "description": "Bi-weekly payroll run",
        "recovery_time_objective_hours": 4,
        "recovery_point_objective_hours": 1,
        "criticality_tier": "tier_1_critical",
    }
    payload.update(overrides)
    return client.post("/api/v1/bcm/processes", headers=headers, json=payload)


def _create_bia(client, headers, process_id, **overrides):
    payload = {
        "impact_analysis_json": {"summary": "Payroll interruption blocks salary disbursement"},
        "financial_impact_tier": "severe",
        "review_frequency_months": 12,
    }
    payload.update(overrides)
    return client.post(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers, json=payload)


def test_self_dependency_rejected_on_create(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-selfdep-create")
    headers = org_user["org_headers"]
    resp = _create_process(
        client,
        headers,
        name="Order Fulfillment",
        dependencies_json=[{"type": "process", "name": "Order Fulfillment"}],
    )
    assert resp.status_code == 400, resp.text
    assert "cannot list itself" in resp.text


def test_self_dependency_rejected_on_update(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-selfdep-update")
    headers = org_user["org_headers"]
    resp = _create_process(client, headers, name="Claims Intake")
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/bcm/processes/{process_id}",
        headers=headers,
        json={"dependencies_json": [{"type": "process", "name": "Claims Intake"}]},
    )
    assert patch_resp.status_code == 400, patch_resp.text


def test_rto_ceiling_flag_for_critical_process(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-rto-ceiling")
    headers = org_user["org_headers"]
    resp = _create_process(
        client, headers, criticality_tier="tier_1_critical", recovery_time_objective_hours=96
    )
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    bia_resp = _create_bia(client, headers, process_id)
    assert bia_resp.status_code == 201, bia_resp.text

    detail = client.get(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert any("recovery_time_objective_exceeds_recommended_ceiling" in f for f in body["context_flags"])


def test_financial_impact_tier_inconsistency_flagged(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-fin-inconsistent")
    headers = org_user["org_headers"]
    resp = _create_process(client, headers, criticality_tier="tier_1_critical", recovery_time_objective_hours=4)
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    bia_resp = _create_bia(client, headers, process_id, financial_impact_tier="low")
    assert bia_resp.status_code == 201, bia_resp.text

    detail = client.get(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert any("financial_impact_tier_inconsistent_with_process_criticality" in f for f in body["context_flags"])


def test_dependency_on_missing_process_flagged(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-dep-missing")
    headers = org_user["org_headers"]
    resp = _create_process(
        client,
        headers,
        name="Customer Support",
        dependencies_json=[{"type": "process", "name": "Nonexistent Upstream Process"}],
    )
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    bia_resp = _create_bia(client, headers, process_id)
    assert bia_resp.status_code == 201, bia_resp.text

    detail = client.get(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert any("dependency_process_not_found_or_inactive" in f for f in body["context_flags"])


def test_no_bia_yet_surfaces_staleness_on_detail_endpoint(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-no-bia-detail")
    headers = org_user["org_headers"]
    resp = _create_process(client, headers)
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    detail = client.get(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["is_stale"] is True
    assert any("No BIA assessment" in f for f in body["context_flags"])


def test_archived_process_excluded_from_overdue_reviews(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-archived-overdue")
    headers = org_user["org_headers"]
    resp = _create_process(client, headers, name="Legacy Batch Job")
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    # Never reviewed -> would show up as overdue while active...
    overdue_before = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_before.status_code == 200, overdue_before.text
    assert any(item["process_id"] == process_id for item in overdue_before.json()["items"])

    # ...but once archived, it's no longer a continuity-review candidate.
    archive_resp = client.patch(
        f"/api/v1/bcm/processes/{process_id}",
        headers=headers,
        json={"status": "archived"},
    )
    assert archive_resp.status_code == 200, archive_resp.text

    overdue_after = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_after.status_code == 200, overdue_after.text
    assert not any(item["process_id"] == process_id for item in overdue_after.json()["items"])
