from __future__ import annotations

from decimal import Decimal

import pandas as pd

from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
MONITORING_BASE = "/api/v1/ai-governance/monitoring"
ALERTS_BASE = "/api/v1/compliance/monitoring/alerts"


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
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_config(
    client,
    headers: dict[str, str],
    system_id: str,
    *,
    metric_type: str,
    threshold_value: float,
    comparison_direction: str,
    baseline_value: float,
    api_key: str,
) -> str:
    resp = client.post(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs",
        headers=headers,
        json={
            "metric_type": metric_type,
            "threshold_value": threshold_value,
            "comparison_direction": comparison_direction,
            "alert_on_breach": True,
            "check_frequency": "daily",
            "baseline_value": baseline_value,
            "api_key": api_key,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_drift_metric_history_endpoint_returns_time_series_and_trend(client):
    org = bootstrap_org_user(client, email_prefix="t111-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Drift System")
    config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        metric_type="output_drift",
        threshold_value=0.3,
        comparison_direction="above",
        baseline_value=0.05,
        api_key="t111-drift-key-123456",
    )

    # Simulate drift readings increasing over time (as a satellite would push).
    for value in (0.05, 0.10, 0.20, 0.45):
        resp = client.post(
            f"{MONITORING_BASE}/readings",
            headers=org["org_headers"],
            json={"config_id": config_id, "value": value, "source_tool": "evidently"},
        )
        assert resp.status_code == 201

    history = client.get(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs/{config_id}/readings",
        headers=org["org_headers"],
    )
    assert history.status_code == 200
    body = history.json()
    assert body["metric_type"] == "output_drift"
    assert body["total"] == 4
    assert len(body["readings"]) == 4
    # readings are newest-first; last reading (0.45) breached the 0.3 threshold.
    assert body["readings"][0]["value"] == "0.4500"
    assert body["readings"][0]["within_threshold"] is False
    summary = body["summary"]
    assert summary["max_value"] == "0.4500"
    assert summary["min_value"] == "0.0500"
    assert summary["trend_direction"] == "increasing"
    assert summary["pct_from_baseline"] > 0

    # Org isolation on the history endpoint.
    org_b = bootstrap_org_user(client, email_prefix="t111-org-b")
    forbidden = client.get(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs/{config_id}/readings",
        headers=org_b["org_headers"],
    )
    assert forbidden.status_code == 404


def test_sustained_degradation_escalates_alert_severity_with_context(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t113-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Degradation System")
    config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        metric_type="accuracy",
        threshold_value=0.9,
        comparison_direction="below",
        baseline_value=0.95,
        api_key="t113-degrade-key-123456",
    )

    # First breach: single point-in-time dip, not yet a sustained trend.
    first = client.post(
        f"{MONITORING_BASE}/readings",
        headers=org["org_headers"],
        json={"config_id": config_id, "value": 0.88, "source_tool": "manual"},
    )
    assert first.status_code == 201

    alerts = client.get(f"{ALERTS_BASE}?alert_type=ai_monitoring", headers=org["org_headers"])
    first_alert = next(a for a in alerts.json() if a["alert_context_json"]["config_id"] == config_id)
    assert first_alert["alert_context_json"]["breach_streak"] == 1
    assert first_alert["alert_context_json"]["sustained_degradation"] is False
    assert first_alert["severity"] == "high"  # accuracy maps to "high" base severity

    # Two more consecutive breaches -> sustained degradation, severity escalates.
    for value in (0.85, 0.80):
        resp = client.post(
            f"{MONITORING_BASE}/readings",
            headers=org["org_headers"],
            json={"config_id": config_id, "value": value, "source_tool": "manual"},
        )
        assert resp.status_code == 201

    alerts_after = client.get(f"{ALERTS_BASE}?alert_type=ai_monitoring", headers=org["org_headers"])
    matching = [a for a in alerts_after.json() if a["alert_context_json"]["config_id"] == config_id]
    latest_alert = sorted(matching, key=lambda a: a["created_at"])[-1]
    assert latest_alert["alert_context_json"]["breach_streak"] == 3
    assert latest_alert["alert_context_json"]["sustained_degradation"] is True
    assert latest_alert["severity"] == "critical"
    assert "sustained degradation" in latest_alert["description"]
    assert "3 consecutive breaches" in latest_alert["description"]
    assert "vs baseline" in latest_alert["description"]

    from sqlalchemy import text

    audit_rows = db_session.execute(
        text(
            "SELECT organization_id, action, entity_type, metadata_json FROM audit_logs "
            "WHERE action = 'monitoring.breach' ORDER BY created_at"
        )
    ).fetchall()
    assert len(audit_rows) == 3
    expected_org = org["organization_id"].replace("-", "")
    assert all(str(row[0]).replace("-", "") == expected_org for row in audit_rows)
    assert all(row[1] == "monitoring.breach" and row[2] == "control_monitoring_alert" for row in audit_rows)


def test_fairness_and_drift_runner_compute_real_metrics_and_push_to_core(client, monkeypatch):
    """End-to-end: the satellite adapters compute a real statistical metric
    (Evidently drift share / AIF360 disparate-impact gap) and the runner
    pushes it into core's actual inbound endpoint, which stores a reading,
    checks the threshold, and (on breach) creates a real alert + audit row.
    """
    from app.satellites.llm_observability.models import MonitoringIngestTarget
    from app.satellites.llm_observability.runner import (
        run_drift_check_and_push,
        run_fairness_check_and_push,
    )

    org = bootstrap_org_user(client, email_prefix="t112-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Fairness System")
    fairness_config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        metric_type="bias_parity_gap",
        threshold_value=0.2,
        comparison_direction="above",
        baseline_value=0.0,
        api_key="t112-fair-key-1234567",
    )
    drift_config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        metric_type="output_drift",
        threshold_value=0.9,
        comparison_direction="above",
        baseline_value=0.0,
        api_key="t112-drift-key-1234567",
    )

    # Patch httpx.Client used by CoreMonitoringIngestClient to call the real
    # in-process TestClient instead of a real network socket.
    import app.satellites.llm_observability.ingest_client as ingest_client_module

    class _TestClientAdapter:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            path = url.split("://", 1)[1].split("/", 1)[1]
            return client.post("/" + path, headers=headers, json=json)

    monkeypatch.setattr(ingest_client_module, "httpx", type("_M", (), {"Client": _TestClientAdapter}))

    fairness_df = pd.DataFrame(
        {
            "label": [1, 1, 1, 0, 1, 0, 0, 0],
            "prediction": [1, 1, 0, 0, 1, 0, 0, 1],
            "protected": [1, 1, 1, 1, 0, 0, 0, 0],
        }
    )
    fairness_result = run_fairness_check_and_push(
        target=MonitoringIngestTarget(
            base_url="https://core.internal", api_key="t112-fair-key-1234567", config_id=fairness_config_id
        ),
        dataframe=fairness_df,
        label_column="label",
        prediction_column="prediction",
        protected_attribute="protected",
        privileged_value=1,
        unprivileged_value=0,
        method="aif360",
    )
    assert fairness_result["pushed"]["within_threshold"] is False  # gap 0.667 > 0.2 threshold

    reference = pd.DataFrame({"score": [0.1, 0.2, 0.3, 0.4, 0.5], "label": [0, 0, 1, 1, 1]})
    current = pd.DataFrame({"score": [0.6, 0.7, 0.8, 0.9, 1.0], "label": [1, 1, 1, 1, 1]})
    drift_result = run_drift_check_and_push(
        target=MonitoringIngestTarget(
            base_url="https://core.internal", api_key="t112-drift-key-1234567", config_id=drift_config_id
        ),
        reference_data=reference,
        current_data=current,
    )
    assert "id" in drift_result["pushed"]

    history = client.get(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs/{fairness_config_id}/readings",
        headers=org["org_headers"],
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert Decimal(history.json()["readings"][0]["value"]) > Decimal("0.6")
