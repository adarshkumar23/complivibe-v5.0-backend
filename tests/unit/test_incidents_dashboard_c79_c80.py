from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.data_asset import DataAsset
from app.models.data_incident import DataIncident
from app.models.issue import Issue
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
ACCESS_BASE = "/api/v1/data-observability/access"
QUALITY_BASE = "/api/v1/data-observability/quality"
LINEAGE_BASE = "/api/v1/data-observability/lineage"
RETENTION_BASE = "/api/v1/data-observability/retention"
INCIDENTS_BASE = "/api/v1/data-observability/incidents"
DASHBOARD_BASE = "/api/v1/data-observability/dashboard"


def _create_asset(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    response = client.post(
        ASSETS_BASE,
        headers=headers,
        json={
            "name": name,
            "asset_type": "table",
            "owner_id": owner_id,
            "description": "asset for incidents and dashboard",
            "schema_column_names": ["customer_id", "email"],
            "permitted_regions": ["US"],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _configure_ingest_key(client, headers: dict[str, str], api_key: str | None = None) -> str:
    # Access-monitoring uses its own key_type now; return the provisioned key.
    response = client.post(
        "/api/v1/integrations/ingest-keys",
        headers=headers,
        json={"key_type": "access_monitoring"},
    )
    assert response.status_code == 201, response.text
    return response.json()["api_key"]


def test_c79_data_incident_detection(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c79-org")
    asset_id = _create_asset(client, org["org_headers"], org["user_id"], "c79_asset")

    # Manual critical incident auto-creates linked issue.
    critical = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "manual",
            "title": "Critical exfiltration",
            "description": "Large unauthorized export detected",
            "severity": "critical",
            "detected_by": "manual",
        },
    )
    assert critical.status_code == 201
    critical_body = critical.json()
    assert critical_body["linked_issue_id"] is not None
    issue = db_session.get(Issue, uuid.UUID(critical_body["linked_issue_id"]))
    assert issue is not None
    assert issue.source_type == "data_incident"
    assert str(issue.source_id) == critical_body["id"]

    # Medium incident should not auto-escalate.
    medium = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "quality_breach",
            "title": "Metric drift",
            "description": "Freshness dropped below threshold",
            "severity": "medium",
            "rule_type": "freshness",
            "detected_by": "api",
        },
    )
    assert medium.status_code == 201
    medium_body = medium.json()
    assert medium_body["linked_issue_id"] is None

    # Dedup same asset+detector+rule within 1 hour.
    medium_dup = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "quality_breach",
            "title": "Metric drift duplicate",
            "description": "Another event in window",
            "severity": "medium",
            "rule_type": "freshness",
            "detected_by": "api",
        },
    )
    assert medium_dup.status_code == 201
    assert medium_dup.json()["id"] == medium_body["id"]
    assert medium_dup.json()["recurrence_count"] >= 2
    assert "repeated_incident" in medium_dup.json()["context_flags"]

    # A duplicate inside the dedup window with higher severity should upgrade the same incident.
    medium_critical_dup = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "quality_breach",
            "title": "Metric drift escalated",
            "description": "Escalated impact within dedup window",
            "severity": "critical",
            "rule_type": "freshness",
            "detected_by": "api",
        },
    )
    assert medium_critical_dup.status_code == 201
    assert medium_critical_dup.json()["id"] == medium_body["id"]
    assert medium_critical_dup.json()["severity"] == "critical"
    assert medium_critical_dup.json()["linked_issue_id"] is not None
    assert medium_critical_dup.json()["escalated_to_issue"] is True

    investigate = client.post(f"{INCIDENTS_BASE}/{medium_body['id']}/investigate", headers=org["org_headers"])
    assert investigate.status_code == 200
    assert investigate.json()["status"] == "investigating"

    resolve = client.post(
        f"{INCIDENTS_BASE}/{medium_body['id']}/resolve",
        headers=org["org_headers"],
        json={"notes": "Mitigation deployed"},
    )
    assert resolve.status_code == 200
    assert resolve.json()["status"] == "resolved"
    assert resolve.json()["resolved_at"] is not None

    # Manual escalation for medium incident.
    medium_2 = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "manual",
            "title": "Manual review required",
            "description": "Escalate this medium incident",
            "severity": "medium",
            "rule_type": "manual_escalation_path",
            "detected_by": "manual",
        },
    )
    assert medium_2.status_code == 201
    medium_2_id = medium_2.json()["id"]
    assert "untriaged" in medium_2.json()["context_flags"]
    stale_row = db_session.get(DataIncident, uuid.UUID(medium_2_id))
    assert stale_row is not None
    stale_row.detected_at = datetime.now(UTC) - timedelta(hours=30)
    stale_row.updated_at = stale_row.detected_at
    db_session.commit()

    escalated = client.post(f"{INCIDENTS_BASE}/{medium_2_id}/escalate-to-issue", headers=org["org_headers"])
    assert escalated.status_code == 200
    escalated_issue = db_session.get(Issue, uuid.UUID(escalated.json()["issue_id"]))
    assert escalated_issue is not None
    assert escalated_issue.source_type == "data_incident"

    summary = client.get(f"{INCIDENTS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["by_severity"].get("critical", 0) >= 1
    assert summary_body["by_severity"].get("medium", 0) >= 1
    assert "open_count" in summary_body
    assert "critical_open_count" in summary_body
    assert "mean_time_to_resolve_hours" in summary_body
    assert "context_flags" in summary_body
    assert summary_body["open_count"] >= 1
    assert summary_body["stale_new_count"] >= 1
    assert "stale_new_incidents_present" in summary_body["context_flags"]

    # Wire test: access anomaly breach creates incident.
    ingest_key = _configure_ingest_key(client, org["org_headers"])

    custom_rule = client.post(
        f"{ACCESS_BASE}/anomaly-rules",
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "rule_type": "access_count_spike",
            "rule_config": {"count": 0, "window_minutes": 10},
        },
    )
    assert custom_rule.status_code == 201

    ingest = client.post(
        f"{ACCESS_BASE}/events",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "data_asset_id": asset_id,
            "access_type": "read",
            "access_result": "success",
            "access_time": datetime.now(UTC).isoformat(),
            "source_country": "US",
            "metadata": {"case": "wire-test"},
        },
    )
    assert ingest.status_code == 201

    incidents = client.get(
        f"{INCIDENTS_BASE}?data_asset_id={asset_id}&detector_type=anomaly_rule",
        headers=org["org_headers"],
    )
    assert incidents.status_code == 200
    assert len(incidents.json()) >= 1
    assert "age_hours" in incidents.json()[0]
    assert "context_flags" in incidents.json()[0]

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="c79-org-b")
    isolated = client.get(INCIDENTS_BASE, headers=org_b["org_headers"])
    assert isolated.status_code == 200
    assert isolated.json() == []


def test_resolved_incident_is_terminal(client):
    org = bootstrap_org_user(client, email_prefix="c79-terminal-resolved")
    asset_id = _create_asset(client, org["org_headers"], org["user_id"], "c79_terminal_resolved")

    created = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "manual",
            "title": "Resolve then lock",
            "description": "Terminal transition guard",
            "severity": "medium",
            "detected_by": "manual",
        },
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    resolved = client.post(
        f"{INCIDENTS_BASE}/{incident_id}/resolve",
        headers=org["org_headers"],
        json={"notes": "Handled"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    investigate = client.post(f"{INCIDENTS_BASE}/{incident_id}/investigate", headers=org["org_headers"])
    assert investigate.status_code == 422
    assert "Cannot transition from terminal status 'resolved'" in investigate.text


def test_dismissed_incident_is_terminal(client):
    org = bootstrap_org_user(client, email_prefix="c79-terminal-dismissed")
    asset_id = _create_asset(client, org["org_headers"], org["user_id"], "c79_terminal_dismissed")

    created = client.post(
        INCIDENTS_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_id,
            "detector_type": "manual",
            "title": "Dismiss then lock",
            "description": "Terminal transition guard",
            "severity": "medium",
            "detected_by": "manual",
        },
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    dismissed = client.post(f"{INCIDENTS_BASE}/{incident_id}/dismiss", headers=org["org_headers"])
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    contain = client.post(f"{INCIDENTS_BASE}/{incident_id}/contain", headers=org["org_headers"])
    assert contain.status_code == 422
    assert "Cannot transition from terminal status 'dismissed'" in contain.text


def test_c80_data_observability_dashboard(client, db_session):
    unauth = client.get(DASHBOARD_BASE)
    assert unauth.status_code in {400, 401, 403}

    org = bootstrap_org_user(client, email_prefix="c80-org")
    asset_1 = _create_asset(client, org["org_headers"], org["user_id"], "c80_personal")
    asset_2 = _create_asset(client, org["org_headers"], org["user_id"], "c80_unclassified")

    # Confirm one classification.
    confirm = client.post(
        f"{ASSETS_BASE}/{asset_1}/confirm-classification",
        headers=org["org_headers"],
        json={"classification_type": "personal_data", "sensitivity_tier": "restricted"},
    )
    assert confirm.status_code == 200

    # Quality readings including one breach.
    q_cfg = client.post(
        f"{QUALITY_BASE}/configs",
        headers=org["org_headers"],
        json={
            "data_asset_id": asset_1,
            "metric_type": "freshness",
            "threshold_value": 0.95,
            "comparison_direction": "below",
            "alert_on_breach": True,
            "measurement_frequency": "daily",
        },
    )
    assert q_cfg.status_code == 201
    q_cfg_id = q_cfg.json()["id"]

    q_breach = client.post(
        f"{QUALITY_BASE}/configs/{q_cfg_id}/readings",
        headers=org["org_headers"],
        json={"value": 1.10, "source_tool": "great_expectations"},
    )
    assert q_breach.status_code == 201

    q_pass = client.post(
        f"{QUALITY_BASE}/configs/{q_cfg_id}/readings",
        headers=org["org_headers"],
        json={"value": 0.90, "source_tool": "great_expectations"},
    )
    assert q_pass.status_code == 201

    # Access anomaly incident for anomaly_count_7d.
    ingest_key = _configure_ingest_key(client, org["org_headers"])
    custom_rule = client.post(
        f"{ACCESS_BASE}/anomaly-rules",
        headers=org["org_headers"],
        json={"data_asset_id": asset_1, "rule_type": "mass_download", "rule_config": {"bytes": 100}},
    )
    assert custom_rule.status_code == 201

    ingest = client.post(
        f"{ACCESS_BASE}/events",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "data_asset_id": asset_1,
            "access_type": "export",
            "access_result": "success",
            "bytes_transferred": 500,
            "access_time": datetime.now(UTC).isoformat(),
            "source_country": "US",
            "metadata": {"case": "dashboard"},
        },
    )
    assert ingest.status_code == 201

    # Pending retention review.
    policy = client.post(
        f"{RETENTION_BASE}/policies",
        headers=org["org_headers"],
        json={"name": "30 days", "retention_days": 30, "action_on_expiry": "flag"},
    )
    assert policy.status_code == 201

    apply_policy = client.post(
        f"{RETENTION_BASE}/policies/{policy.json()['id']}/apply-to-asset",
        headers=org["org_headers"],
        json={"data_asset_id": asset_2},
    )
    assert apply_policy.status_code == 200

    row = db_session.get(DataAsset, uuid.UUID(asset_2))
    assert row is not None
    row.retention_review_date = (datetime.now(UTC) - timedelta(days=15)).date()
    db_session.commit()

    sweep = client.post(f"{RETENTION_BASE}/trigger-sweep", headers=org["org_headers"])
    assert sweep.status_code == 200

    dash = client.get(DASHBOARD_BASE, headers=org["org_headers"])
    assert dash.status_code == 200
    body = dash.json()

    for key in [
        "asset_coverage",
        "quality_metrics",
        "access_anomalies",
        "retention",
        "data_obligation_coverage",
        "generated_at",
    ]:
        assert key in body

    assert body["asset_coverage"]["total_assets"] == 2
    assert body["quality_metrics"]["breach_count_7d"] >= 1
    assert body["access_anomalies"]["anomaly_count_7d"] >= 1
    assert body["retention"]["pending_reviews"] >= 1
    assert "status" not in body["data_obligation_coverage"]
    assert "coverage_pct" in body["data_obligation_coverage"]

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="c80-org-b")
    dash_b = client.get(DASHBOARD_BASE, headers=org_b["org_headers"])
    assert dash_b.status_code == 200
    assert dash_b.json()["asset_coverage"]["total_assets"] == 0
