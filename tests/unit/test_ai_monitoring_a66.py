from __future__ import annotations

from pathlib import Path

from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
MONITORING_BASE = "/api/v1/ai-governance/monitoring"
INBOUND_BASE = "/api/v1/ai-monitoring"
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
            "baseline_value": threshold_value,
            "api_key": api_key,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["api_key_configured"] is True
    return resp.json()["id"]


def test_a66_monitoring_mode_b(client):
    org = bootstrap_org_user(client, email_prefix="a66-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "A66 System")

    config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        metric_type="response_time",
        threshold_value=200.0,
        comparison_direction="above",
        api_key="a66-key-123456789",
    )

    # Within threshold (above): value <= threshold
    within = client.post(
        f"{MONITORING_BASE}/readings",
        headers=org["org_headers"],
        json={"config_id": config_id, "value": 120.0, "source_tool": "manual_runner"},
    )
    assert within.status_code == 201
    assert within.json()["within_threshold"] is True

    alerts_after_within = client.get(f"{ALERTS_BASE}?alert_type=ai_monitoring", headers=org["org_headers"])
    assert alerts_after_within.status_code == 200
    assert alerts_after_within.json() == []

    # Breach (above): value > threshold
    breach_above = client.post(
        f"{MONITORING_BASE}/readings",
        headers=org["org_headers"],
        json={"config_id": config_id, "value": 250.0, "source_tool": "manual_runner"},
    )
    assert breach_above.status_code == 201
    assert breach_above.json()["within_threshold"] is False

    alerts_after_breach = client.get(f"{ALERTS_BASE}?alert_type=ai_monitoring", headers=org["org_headers"])
    assert alerts_after_breach.status_code == 200
    assert len(alerts_after_breach.json()) >= 1

    # Breach (below): value < threshold
    below_config_id = _create_config(
        client,
        org["org_headers"],
        system_id,
        metric_type="accuracy",
        threshold_value=0.9,
        comparison_direction="below",
        api_key="a66-key-098765432",
    )
    breach_below = client.post(
        f"{MONITORING_BASE}/readings",
        headers=org["org_headers"],
        json={"config_id": below_config_id, "value": 0.8, "source_tool": "manual_runner"},
    )
    assert breach_below.status_code == 201
    assert breach_below.json()["within_threshold"] is False

    # Config gets last_checked_at + last_reading_value updated.
    configs = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-configs", headers=org["org_headers"])
    assert configs.status_code == 200
    by_id = {row["id"]: row for row in configs.json()}
    assert by_id[config_id]["last_checked_at"] is not None
    assert float(by_id[config_id]["last_reading_value"]) == 250.0

    # Monitoring dashboard returns config states and recent breaches.
    dashboard = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-dashboard", headers=org["org_headers"])
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert len(body["configs"]) >= 2
    assert len(body["recent_breaches"]) >= 2

    # Inbound endpoint valid API key.
    inbound_ok = client.post(
        f"{INBOUND_BASE}/readings",
        headers={"X-CompliVibe-Key": "a66-key-123456789"},
        json={
            "config_id": config_id,
            "value": 190.0,
            "metric_type": "response_time",
            "source_tool": "external_monitor",
        },
    )
    assert inbound_ok.status_code == 201
    assert inbound_ok.json()["reading_source"] == "api_report"

    # Inbound invalid key.
    inbound_bad = client.post(
        f"{INBOUND_BASE}/readings",
        headers={"X-CompliVibe-Key": "wrong-key"},
        json={
            "config_id": config_id,
            "value": 180.0,
            "metric_type": "response_time",
            "source_tool": "external_monitor",
        },
    )
    assert inbound_bad.status_code == 401

    # Deactivate config -> submit rejected.
    deactivated = client.post(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs/{config_id}/deactivate",
        headers=org["org_headers"],
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    rejected = client.post(
        f"{MONITORING_BASE}/readings",
        headers=org["org_headers"],
        json={"config_id": config_id, "value": 100.0, "source_tool": "manual_runner"},
    )
    assert rejected.status_code == 422

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a66-org-b")
    forbidden = client.post(
        f"{MONITORING_BASE}/readings",
        headers=org_b["org_headers"],
        json={"config_id": below_config_id, "value": 1.0, "source_tool": "manual_runner"},
    )
    assert forbidden.status_code == 404

    source = Path("app/ai_governance/services/ai_monitoring_service.py").read_text(encoding="utf-8").lower()
    assert "evidently" not in source
    assert "nannyml" not in source
