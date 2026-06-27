from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
LINEAGE_BASE = "/api/v1/data-observability/lineage"
QUALITY_BASE = "/api/v1/data-observability/quality"
ALERTS_BASE = "/api/v1/compliance/monitoring/alerts"


def _create_asset(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    resp = client.post(
        ASSETS_BASE,
        headers=headers,
        json={
            "name": name,
            "asset_type": "table",
            "owner_id": owner_id,
            "description": "Asset for lineage/quality tests",
            "schema_column_names": ["email", "customer_id"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_c75_lineage_tracking(client):
    org = bootstrap_org_user(client, email_prefix="c75-org")
    asset_id = _create_asset(client, org["org_headers"], org["user_id"], "customer_email_table")

    node_a = client.post(
        f"{LINEAGE_BASE}/nodes",
        headers=org["org_headers"],
        json={"node_type": "pipeline_step", "name": "extract_customers", "system_name": "Airflow"},
    )
    assert node_a.status_code == 201
    node_a_id = node_a.json()["id"]

    duplicate_node = client.post(
        f"{LINEAGE_BASE}/nodes",
        headers=org["org_headers"],
        json={"node_type": "pipeline_step", "name": "extract_customers", "system_name": "Airflow"},
    )
    assert duplicate_node.status_code == 201
    assert duplicate_node.json()["id"] == node_a_id

    node_b = client.post(
        f"{LINEAGE_BASE}/nodes",
        headers=org["org_headers"],
        json={"node_type": "data_asset", "name": "warehouse.customers", "system_name": "dbt"},
    )
    assert node_b.status_code == 201
    node_b_id = node_b.json()["id"]

    linked = client.post(
        f"{LINEAGE_BASE}/nodes/{node_b_id}/link-asset/{asset_id}",
        headers=org["org_headers"],
    )
    assert linked.status_code == 200
    assert linked.json()["data_asset_id"] == asset_id

    edge = client.post(
        f"{LINEAGE_BASE}/edges",
        headers=org["org_headers"],
        json={
            "upstream_node_id": node_a_id,
            "downstream_node_id": node_b_id,
            "transformation_description": "copy",
            "metadata": {"mode": "full"},
        },
    )
    assert edge.status_code == 201
    assert edge.json()["source_method"] == "manual"

    duplicate_edge = client.post(
        f"{LINEAGE_BASE}/edges",
        headers=org["org_headers"],
        json={
            "upstream_node_id": node_a_id,
            "downstream_node_id": node_b_id,
            "transformation_description": "copy",
            "metadata": {"mode": "full"},
        },
    )
    assert duplicate_edge.status_code == 409

    graph = client.get(
        f"{LINEAGE_BASE}/assets/{asset_id}/lineage?depth=3",
        headers=org["org_headers"],
    )
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) >= 1
    assert len(graph.json()["edges"]) >= 1

    configured = client.post(
        f"{LINEAGE_BASE}/openmetadata/configure",
        headers=org["org_headers"],
        json={
            "base_url": "https://openmetadata.example.com",
            "jwt_token": "dummy-token",
            "org_api_key": "c75-lineage-api-key-12345",
        },
    )
    assert configured.status_code == 200

    event_payload = {
        "eventType": "COMPLETE",
        "eventTime": "2026-06-26T12:00:00Z",
        "job": {"name": "daily_lineage_job", "namespace": "analytics"},
        "run": {"runId": "abc-123"},
        "inputs": [{"name": "raw.customers", "namespace": "db"}],
        "outputs": [{"name": "warehouse.customers", "namespace": "db"}],
    }

    inbound_ok = client.post(
        f"{LINEAGE_BASE}/events",
        headers={"X-CompliVibe-Key": "c75-lineage-api-key-12345"},
        json=event_payload,
    )
    assert inbound_ok.status_code == 201
    assert inbound_ok.json()["edges_created"] >= 1

    inbound_repeat = client.post(
        f"{LINEAGE_BASE}/events",
        headers={"X-CompliVibe-Key": "c75-lineage-api-key-12345"},
        json=event_payload,
    )
    assert inbound_repeat.status_code == 201
    assert inbound_repeat.json()["edges_created"] == 0

    inbound_bad = client.post(
        f"{LINEAGE_BASE}/events",
        headers={"X-CompliVibe-Key": "wrong-key"},
        json=event_payload,
    )
    assert inbound_bad.status_code == 401

    org_b = bootstrap_org_user(client, email_prefix="c75-org-b")
    forbidden = client.get(f"{LINEAGE_BASE}/assets/{asset_id}/lineage", headers=org_b["org_headers"])
    assert forbidden.status_code == 404


def test_c76_quality_metrics(client):
    org = bootstrap_org_user(client, email_prefix="c76-org")
    personal_asset_id = _create_asset(client, org["org_headers"], org["user_id"], "customer_email_records")
    other_asset_id = _create_asset(client, org["org_headers"], org["user_id"], "operational_logs")

    cfg_breach = client.post(
        f"{QUALITY_BASE}/configs",
        headers=org["org_headers"],
        json={
            "data_asset_id": personal_asset_id,
            "metric_type": "freshness",
            "threshold_value": 0.95,
            "comparison_direction": "below",
            "alert_on_breach": True,
            "measurement_frequency": "daily",
        },
    )
    assert cfg_breach.status_code == 201
    cfg_breach_id = cfg_breach.json()["id"]

    reading_breach = client.post(
        f"{QUALITY_BASE}/configs/{cfg_breach_id}/readings",
        headers=org["org_headers"],
        json={"value": 0.90, "source_tool": "great_expectations", "notes": "late batch"},
    )
    assert reading_breach.status_code == 201
    assert reading_breach.json()["within_threshold"] is False

    alerts = client.get(f"{ALERTS_BASE}?alert_type=data_quality", headers=org["org_headers"])
    assert alerts.status_code == 200
    assert len(alerts.json()) >= 1
    assert alerts.json()[0]["severity"] == "high"

    cfg_ok = client.post(
        f"{QUALITY_BASE}/configs",
        headers=org["org_headers"],
        json={
            "data_asset_id": other_asset_id,
            "metric_type": "accuracy",
            "threshold_value": 0.95,
            "comparison_direction": "above",
            "alert_on_breach": True,
            "measurement_frequency": "daily",
        },
    )
    assert cfg_ok.status_code == 201
    cfg_ok_id = cfg_ok.json()["id"]

    reading_ok = client.post(
        f"{QUALITY_BASE}/configs/{cfg_ok_id}/readings",
        headers=org["org_headers"],
        json={"value": 0.90, "source_tool": "dbt_test"},
    )
    assert reading_ok.status_code == 201
    assert reading_ok.json()["within_threshold"] is True

    cfg_refreshed = client.get(f"{QUALITY_BASE}/configs/{cfg_ok_id}", headers=org["org_headers"])
    assert cfg_refreshed.status_code == 200
    assert float(cfg_refreshed.json()["last_value"]) == 0.90

    deactivated = client.post(f"{QUALITY_BASE}/configs/{cfg_ok_id}/deactivate", headers=org["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    rejected = client.post(
        f"{QUALITY_BASE}/configs/{cfg_ok_id}/readings",
        headers=org["org_headers"],
        json={"value": 0.80, "source_tool": "dbt_test"},
    )
    assert rejected.status_code == 422

    dashboard = client.get(f"{QUALITY_BASE}/dashboard", headers=org["org_headers"])
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["total_configs"] >= 2
    assert body["recent_breaches_7d"] >= 1
    assert "freshness" in body["by_metric_type"]

    asset_configs = client.get(f"{ASSETS_BASE}/{personal_asset_id}/quality-configs", headers=org["org_headers"])
    assert asset_configs.status_code == 200
    assert len(asset_configs.json()) >= 1

    org_b = bootstrap_org_user(client, email_prefix="c76-org-b")
    forbidden = client.get(f"{QUALITY_BASE}/configs/{cfg_breach_id}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404
