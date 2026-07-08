from __future__ import annotations

import time

from tests.helpers.auth_org import bootstrap_org_user


def _create_risk(client, headers, **overrides):
    payload = {
        "title": "Ransomware attack on core systems",
        "category": "operational",
        "likelihood": 3,
        "impact": 4,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/risks", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _fair_payload(**overrides):
    payload = {
        "methodology": "fair",
        "input_parameters": {
            "threat_event_frequency": {"min": 1, "most_likely": 5, "max": 20},
            "vulnerability": {"min": 0.1, "most_likely": 0.3, "max": 0.6},
            "primary_loss_magnitude": {"min": 10000, "most_likely": 100000, "max": 500000},
        },
        "n_iterations": 5000,
    }
    payload.update(overrides)
    return payload


def test_first_run_flags_no_appetite_and_no_prior_run(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-polish-first")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers, category="unmapped_category")

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_fair_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert "first_quantification_run_for_risk" in body["context_flags"]
    assert "no_appetite_threshold_configured_for_category" in body["context_flags"]
    assert body["percent_change_from_previous_run"] is None
    assert body["appetite_comparison"] is None


def test_appetite_breach_is_flagged_and_escalation_owner_surfaced(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-polish-breach")
    headers = org_user["org_headers"]
    user_id = org_user["user_id"]

    # likelihood=3, impact=4 -> inherent_score=12 (residual is capped at inherent).
    risk_id = _create_risk(client, headers, category="operational")
    patch_resp = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=headers,
        json={"residual_likelihood": 5, "residual_impact": 5},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    residual_score = patch_resp.json()["residual_score"]
    assert residual_score is not None

    threshold_resp = client.post(
        "/api/v1/compliance/risk-appetite",
        headers=headers,
        json={
            "scope_type": "org",
            "risk_category": "operational",
            "max_acceptable_score": max(1, residual_score - 1),
            "escalation_owner_id": user_id,
        },
    )
    assert threshold_resp.status_code == 201, threshold_resp.text

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_fair_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert "risk_score_exceeds_appetite_threshold" in body["context_flags"]
    assert body["appetite_comparison"]["breached"] is True
    assert body["appetite_comparison"]["current_risk_score"] == residual_score
    assert body["appetite_comparison"]["max_acceptable_score"] == residual_score - 1
    assert body["appetite_comparison"]["escalation_owner_id"] == user_id


def test_material_change_from_previous_run_is_flagged_in_history(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-polish-trend")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    small_loss_payload = _fair_payload(
        input_parameters={
            "threat_event_frequency": {"min": 0.1, "most_likely": 0.2, "max": 0.3},
            "vulnerability": {"min": 0.01, "most_likely": 0.02, "max": 0.03},
            "primary_loss_magnitude": {"min": 100, "most_likely": 500, "max": 1000},
        }
    )
    first = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=small_loss_payload)
    assert first.status_code == 201, first.text

    # SQLite's CURRENT_TIMESTAMP (used for computed_at in the test DB) has
    # one-second resolution; sleep past it so run ordering is unambiguous.
    time.sleep(1.1)

    large_loss_payload = _fair_payload(
        input_parameters={
            "threat_event_frequency": {"min": 50, "most_likely": 80, "max": 100},
            "vulnerability": {"min": 0.5, "most_likely": 0.7, "max": 0.9},
            "primary_loss_magnitude": {"min": 500000, "most_likely": 1000000, "max": 5000000},
        }
    )
    second = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=large_loss_payload)
    assert second.status_code == 201, second.text
    body = second.json()

    assert body["percent_change_from_previous_run"] is not None
    assert body["percent_change_from_previous_run"] > 50
    assert "expected_annual_loss_shifted_significantly_from_prior_run" in body["context_flags"]

    history_resp = client.get(f"/api/v1/risks/{risk_id}/quantification-history", headers=headers)
    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()
    assert len(history) == 2
    assert history[0]["id"] == second.json()["id"]
    assert "expected_annual_loss_shifted_significantly_from_prior_run" in history[0]["context_flags"]
    # The oldest run has no prior run to compare against.
    assert history[1]["percent_change_from_previous_run"] is None


def test_risk_updated_after_run_is_flagged_stale(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-polish-stale")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_fair_payload())
    assert resp.status_code == 201, resp.text

    # SQLite's CURRENT_TIMESTAMP (used for computed_at/updated_at in the test
    # DB) has one-second resolution; sleep past it so ordering is unambiguous.
    time.sleep(1.1)

    # Mutate the risk's characterization after the quantification run was computed.
    patch_resp = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=headers,
        json={"likelihood": 5, "impact": 5},
    )
    assert patch_resp.status_code == 200, patch_resp.text

    history_resp = client.get(f"/api/v1/risks/{risk_id}/quantification-history", headers=headers)
    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()
    assert len(history) == 1
    assert "risk_characteristics_changed_since_this_run" in history[0]["context_flags"]
