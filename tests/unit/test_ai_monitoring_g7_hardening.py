from __future__ import annotations

import uuid

from app.models.ai_monitoring_config import AIMonitoringConfig
from sqlalchemy import select
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str, model_version: str = "v1") -> str:
    resp = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
            "model_version": model_version,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_config(client, headers, system_id, *, baseline_value: float, api_key: str) -> str:
    resp = client.post(
        f"{SYSTEMS_BASE}/{system_id}/monitoring-configs",
        headers=headers,
        json={
            "metric_type": "accuracy",
            "threshold_value": 0.5,
            "comparison_direction": "below",
            "alert_on_breach": True,
            "baseline_value": baseline_value,
            "api_key": api_key,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_drift_from_baseline_is_flagged(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-mon-drift")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Drift System")
    config_id = _create_config(client, org["org_headers"], system_id, baseline_value=0.90, api_key="g7-drift-key-123")

    # Submit a reading far away from baseline (0.90 -> 0.50 is > 20% deviation).
    reading = client.post(
        "/api/v1/ai-governance/monitoring/readings",
        headers=org["org_headers"],
        json={"config_id": config_id, "value": 0.50},
    )
    assert reading.status_code == 201

    dashboard = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-dashboard", headers=org["org_headers"])
    assert dashboard.status_code == 200
    item = dashboard.json()["configs"][0]

    # INTELLIGENT: dashboard must surface the drift, not just the raw value.
    assert float(item["baseline_value"]) == 0.9
    assert item["drift_detected"] is True
    assert item["drift_pct"] is not None and float(item["drift_pct"]) > 20

    row = db_session.execute(
        select(AIMonitoringConfig).where(AIMonitoringConfig.id == uuid.UUID(config_id))
    ).scalar_one()
    assert row.baseline_model_version == "v1"


def test_baseline_reassessment_required_after_model_version_change(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-mon-stale")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Stale Baseline System", model_version="v1")
    config_id = _create_config(client, org["org_headers"], system_id, baseline_value=0.9, api_key="g7-stale-key-1234")

    dashboard_before = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-dashboard", headers=org["org_headers"])
    assert dashboard_before.json()["configs"][0]["baseline_reassessment_required"] is False

    # CONTEXT-CONSCIOUS: once the underlying model version changes, a baseline
    # captured against the old version must never be presented as still-current.
    patch = client.patch(
        f"{SYSTEMS_BASE}/{system_id}", headers=org["org_headers"], json={"model_version": "v2"}
    )
    assert patch.status_code == 200
    assert patch.json()["model_version"] == "v2"

    dashboard_after = client.get(f"{SYSTEMS_BASE}/{system_id}/monitoring-dashboard", headers=org["org_headers"])
    assert dashboard_after.status_code == 200
    item = dashboard_after.json()["configs"][0]
    assert item["baseline_reassessment_required"] is True
