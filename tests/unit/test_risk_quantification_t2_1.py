from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.risk_quantification import RiskQuantificationRun
from tests.helpers.auth_org import bootstrap_org_user


def _create_risk(client, headers, **overrides):
    payload = {
        "title": "Ransomware attack on core systems",
        "category": "cyber",
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


def _monte_carlo_payload(**overrides):
    payload = {
        "methodology": "monte_carlo",
        "input_parameters": {
            "frequency": {"distribution": "poisson", "lam": 3},
            "loss_magnitude": {"distribution": "lognormal", "mean": 10.0, "sigma": 1.0},
        },
        "n_iterations": 5000,
    }
    payload.update(overrides)
    return payload


def test_risk_quantification_permissions_seeded(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-perms")

    rows = db_session.execute(
        sa.text(
            "SELECT key FROM permissions WHERE key IN ('financial_risk:read', 'financial_risk:manage')"
        )
    ).scalars().all()
    assert set(rows) == {"financial_risk:read", "financial_risk:manage"}

    response = client.get("/api/v1/auth/permissions", headers=org_user["org_headers"])
    assert response.status_code == 200, response.text
    codes = response.json()["permission_codes"]
    assert "financial_risk:read" in codes
    assert "financial_risk:manage" in codes


def test_fair_quantification_happy_path(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-fair")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_fair_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["expected_annual_loss"] > 0
    ci = body["confidence_intervals_json"]
    assert ci["p05"] <= ci["p50"] <= ci["p95"]

    curve = body["loss_exceedance_curve_json"]
    assert len(curve) > 0
    probs = [point["probability_of_exceedance"] for point in curve]
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))

    input_param_names = set(_fair_payload()["input_parameters"].keys())
    assert body["sensitivity_json"]["most_influential_parameter"] in input_param_names


def test_monte_carlo_quantification_happy_path(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-mc")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_monte_carlo_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["expected_annual_loss"] > 0
    ci = body["confidence_intervals_json"]
    assert ci["p05"] <= ci["p50"] <= ci["p95"]

    curve = body["loss_exceedance_curve_json"]
    assert len(curve) > 0
    probs = [point["probability_of_exceedance"] for point in curve]
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))

    input_param_names = {"frequency", "loss_magnitude"}
    assert body["sensitivity_json"]["most_influential_parameter"] in input_param_names


def test_degenerate_input_min_greater_than_max_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-bad-minmax")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    bad_payload = _fair_payload()
    bad_payload["input_parameters"]["threat_event_frequency"] = {"min": 20, "most_likely": 5, "max": 1}

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=bad_payload)
    assert resp.status_code == 422, resp.text
    assert "threat_event_frequency" in resp.json()["detail"]

    count = db_session.execute(
        sa.select(sa.func.count()).select_from(RiskQuantificationRun).where(
            RiskQuantificationRun.risk_id == uuid.UUID(risk_id)
        )
    ).scalar_one()
    assert count == 0


def test_degenerate_input_missing_required_key_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-bad-missing")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    bad_payload = _fair_payload()
    del bad_payload["input_parameters"]["vulnerability"]

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=bad_payload)
    assert resp.status_code == 422, resp.text

    count = db_session.execute(
        sa.select(sa.func.count()).select_from(RiskQuantificationRun).where(
            RiskQuantificationRun.risk_id == uuid.UUID(risk_id)
        )
    ).scalar_one()
    assert count == 0


def test_degenerate_input_negative_frequency_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-bad-neg")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    bad_payload = _monte_carlo_payload()
    bad_payload["input_parameters"]["frequency"] = {"distribution": "poisson", "lam": -3}

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=bad_payload)
    assert resp.status_code == 422, resp.text

    count = db_session.execute(
        sa.select(sa.func.count()).select_from(RiskQuantificationRun).where(
            RiskQuantificationRun.risk_id == uuid.UUID(risk_id)
        )
    ).scalar_one()
    assert count == 0


def test_quantify_nonexistent_risk_returns_404(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-404")
    headers = org_user["org_headers"]
    fake_risk_id = "00000000-0000-0000-0000-000000000000"

    resp = client.post(f"/api/v1/risks/{fake_risk_id}/quantify", headers=headers, json=_fair_payload())
    assert resp.status_code == 404, resp.text


def test_quantification_history_ordering_and_empty(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-history")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    empty_resp = client.get(f"/api/v1/risks/{risk_id}/quantification-history", headers=headers)
    assert empty_resp.status_code == 200, empty_resp.text
    assert empty_resp.json() == []

    resp1 = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_fair_payload())
    assert resp1.status_code == 201, resp1.text
    resp2 = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=_monte_carlo_payload())
    assert resp2.status_code == 201, resp2.text

    history_resp = client.get(f"/api/v1/risks/{risk_id}/quantification-history", headers=headers)
    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()
    assert len(history) == 2
    # Newest first: the second run created (monte_carlo) should appear before the first (fair).
    assert history[0]["id"] == resp2.json()["id"]
    assert history[1]["id"] == resp1.json()["id"]


def test_history_for_nonexistent_risk_returns_404(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-history-404")
    headers = org_user["org_headers"]
    fake_risk_id = "00000000-0000-0000-0000-000000000000"

    resp = client.get(f"/api/v1/risks/{fake_risk_id}/quantification-history", headers=headers)
    assert resp.status_code == 404, resp.text


def test_sensitivity_identifies_high_variance_parameter(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="rq-sensitivity")
    headers = org_user["org_headers"]
    risk_id = _create_risk(client, headers)

    payload = _fair_payload(
        input_parameters={
            # Enormous range -> dominant driver of variance in the resulting loss.
            "primary_loss_magnitude": {"min": 1000, "most_likely": 50000, "max": 5000000},
            # Tiny range -> minimal variance contribution.
            "threat_event_frequency": {"min": 4.99, "most_likely": 5.0, "max": 5.01},
            "vulnerability": {"min": 0.299, "most_likely": 0.3, "max": 0.301},
        },
        n_iterations=8000,
    )

    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    sensitivity = body["sensitivity_json"]
    assert sensitivity["most_influential_parameter"] == "primary_loss_magnitude"
    ranking = sensitivity["ranking"]
    assert ranking[0]["parameter"] == "primary_loss_magnitude"
    # The top-ranked correlation must exceed the low-variance parameters.
    top_corr = abs(ranking[0]["correlation"])
    for entry in ranking[1:]:
        assert top_corr >= abs(entry["correlation"])
