from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    resp = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
            "model_version": "v1",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_config(
    client, headers: dict[str, str], system_id: str, *, threshold_value: str, comparison_direction: str, api_key: str
) -> str:
    resp = client.post(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs",
        headers=headers,
        json={
            "metric_type": "output_drift",
            "threshold_value": threshold_value,
            "comparison_direction": comparison_direction,
            "alert_on_breach": True,
            "api_key": api_key,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_threshold_breach_alerting_unaffected_by_drift_dashboard_change(client, capsys):
    """Baseline regression guard for the previously-fixed inverted comparator
    (cb84613): reproduces the exact ramp/threshold scenario from that fix so a
    later change to the *dashboard's* drift computation can be proven not to
    have touched submit_reading()/check_threshold()'s breach alerting at all.

    Ramp 0.03 -> 0.33 against threshold_value=0.25, comparison_direction="above":
    only the readings >= 0.25 (0.28, 0.30, 0.33) must breach.
    """
    org = bootstrap_org_user(client, email_prefix="evidently-threshold")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Threshold Baseline System")
    config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        threshold_value="0.25",
        comparison_direction="above",
        api_key="evidently-threshold-key-1",
    )

    ramp = ["0.03", "0.08", "0.13", "0.18", "0.23", "0.28", "0.30", "0.33"]
    results = []
    for value in ramp:
        resp = client.post(
            "/api/v1/ai-governance/monitoring/readings",
            headers=org["org_headers"],
            json={"config_id": config_id, "value": value},
        )
        assert resp.status_code == 201, resp.text
        results.append((value, resp.json()["within_threshold"]))

    print("BASELINE THRESHOLD RESULTS (value, within_threshold):", results)

    breached_values = [value for value, within_threshold in results if not within_threshold]
    healthy_values = [value for value, within_threshold in results if within_threshold]
    assert breached_values == ["0.28", "0.30", "0.33"]
    assert healthy_values == ["0.03", "0.08", "0.13", "0.18", "0.23"]


def test_output_drift_dashboard_uses_real_evidently_not_percent_diff(client, capsys):
    """The dashboard's drift_pct/drift_detected for `output_drift` must come
    from a real Evidently DataDriftPreset computation over reference vs
    current reading windows once enough history exists (>= 2 *
    EVIDENTLY_WINDOW_SIZE readings), not the old scalar
    percent-from-baseline diff. Uses a threshold far out of reach (99) so
    submit_reading()'s own breach alerting never fires and can't be confused
    with the dashboard's drift signal.
    """
    org = bootstrap_org_user(client, email_prefix="evidently-real-drift")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Real Evidently Drift System")
    config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        threshold_value="99",
        comparison_direction="above",
        api_key="evidently-real-drift-key-1",
    )

    # Reference window: a tight, stable cluster -- genuinely no distributional
    # shift within itself when later compared against more of the same.
    stable_values = ["0.10", "0.11", "0.09", "0.10", "0.11"]
    for value in stable_values:
        resp = client.post(
            "/api/v1/ai-governance/monitoring/readings",
            headers=org["org_headers"],
            json={"config_id": config_id, "value": value},
        )
        assert resp.status_code == 201, resp.text

    # Still-stable current window (same distribution as reference): must NOT
    # be flagged as drift.
    more_stable_values = ["0.10", "0.12", "0.09", "0.11", "0.10"]
    for value in more_stable_values:
        resp = client.post(
            "/api/v1/ai-governance/monitoring/readings",
            headers=org["org_headers"],
            json={"config_id": config_id, "value": value},
        )
        assert resp.status_code == 201, resp.text

    dashboard_healthy = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-dashboard", headers=org["org_headers"])
    assert dashboard_healthy.status_code == 200
    healthy_item = dashboard_healthy.json()["configs"][0]
    print("REAL EVIDENTLY (stable current window):", healthy_item["drift_pct"], healthy_item["drift_detected"])
    assert healthy_item["drift_detected"] is False

    # Now push a materially drifted window: real distributional shift, not
    # just a single outlier value.
    drifted_values = ["0.68", "0.72", "0.66", "0.70", "0.69"]
    for value in drifted_values:
        resp = client.post(
            "/api/v1/ai-governance/monitoring/readings",
            headers=org["org_headers"],
            json={"config_id": config_id, "value": value},
        )
        assert resp.status_code == 201, resp.text

    dashboard_drifted = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-dashboard", headers=org["org_headers"])
    assert dashboard_drifted.status_code == 200
    drifted_item = dashboard_drifted.json()["configs"][0]
    print("REAL EVIDENTLY (drifted current window):", drifted_item["drift_pct"], drifted_item["drift_detected"])
    assert drifted_item["drift_detected"] is True
    assert drifted_item["drift_pct"] is not None and float(drifted_item["drift_pct"]) > 0
