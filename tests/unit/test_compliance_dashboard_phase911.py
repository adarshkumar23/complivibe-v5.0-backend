import uuid

from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/dashboard"


def _create_policy(client, headers: dict[str, str], owner_user_id: str, title: str = "Policy") -> dict:
    response = client.post(
        "/api/v1/compliance/policies",
        headers=headers,
        json={
            "title": title,
            "policy_type": "acceptable_use",
            "status": "draft",
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _activate_framework(client, headers: dict[str, str], framework_id: str) -> None:
    response = client.post(f"/api/v1/frameworks/{framework_id}/activate", headers=headers, json={"notes": "phase911"})
    assert response.status_code == 200


def test_phase911_dashboard_endpoint_shapes(client):
    org = bootstrap_org_user(client, email_prefix="p911-shape")

    posture = client.get(f"{BASE}/posture-summary", headers=org["org_headers"])
    assert posture.status_code == 200
    posture_body = posture.json()
    assert set(posture_body.keys()) == {
        "active_frameworks",
        "obligations",
        "controls",
        "evidence",
        "risks",
        "tasks",
        "policies",
        "vendors",
        "monitoring",
        "deadlines",
    }

    readiness = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert readiness.status_code == 200
    assert isinstance(readiness.json(), list)

    control_health = client.get(f"{BASE}/control-health", headers=org["org_headers"])
    assert control_health.status_code == 200
    assert set(control_health.json().keys()) == {
        "total_controls_by_status",
        "controls_with_no_evidence",
        "controls_with_expired_evidence",
        "controls_with_open_monitoring_alerts",
        "controls_with_overdue_checks",
        "controls_mapped_to_0_obligations",
        "open_high_critical_findings",
        "health_flag",
    }

    heatmap = client.get(f"{BASE}/risk-heatmap", headers=org["org_headers"])
    assert heatmap.status_code == 200
    heatmap_body = heatmap.json()
    assert set(heatmap_body.keys()) == {
        "risk_heatmap",
        "vendor_risk_distribution",
        "open_monitoring_alerts_by_severity",
    }
    assert isinstance(heatmap_body["risk_heatmap"], list)
    assert len(heatmap_body["risk_heatmap"]) == 25

    recent = client.get(f"{BASE}/recent-activity?limit=20", headers=org["org_headers"])
    assert recent.status_code == 200
    assert isinstance(recent.json(), list)


def test_phase911_tenant_isolation(client):
    org1 = bootstrap_org_user(client, email_prefix="p911-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="p911-tenant-b")

    _create_policy(client, org1["org_headers"], owner_user_id=org1["user_id"], title="Org1 Policy")

    org1_summary = client.get(f"{BASE}/posture-summary", headers=org1["org_headers"])
    assert org1_summary.status_code == 200
    assert org1_summary.json()["policies"]["total"] >= 1

    org2_summary = client.get(f"{BASE}/posture-summary", headers=org2["org_headers"])
    assert org2_summary.status_code == 200
    assert org2_summary.json()["policies"]["total"] == 0


def test_phase911_empty_org_graceful_responses(client):
    org = bootstrap_org_user(client, email_prefix="p911-empty")

    posture = client.get(f"{BASE}/posture-summary", headers=org["org_headers"])
    assert posture.status_code == 200
    assert posture.json()["active_frameworks"]["count"] == 0

    readiness = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert readiness.status_code == 200
    assert readiness.json() == []

    control_health = client.get(f"{BASE}/control-health", headers=org["org_headers"])
    assert control_health.status_code == 200

    heatmap = client.get(f"{BASE}/risk-heatmap", headers=org["org_headers"])
    assert heatmap.status_code == 200

    recent = client.get(f"{BASE}/recent-activity", headers=org["org_headers"])
    assert recent.status_code == 200


def test_phase911_no_audit_writes_for_read_endpoints(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p911-audit")

    org_uuid = uuid.UUID(org["organization_id"])
    before_count = db_session.query(AuditLog).filter(AuditLog.organization_id == org_uuid).count()

    assert client.get(f"{BASE}/posture-summary", headers=org["org_headers"]).status_code == 200
    assert client.get(f"{BASE}/framework-readiness", headers=org["org_headers"]).status_code == 200
    assert client.get(f"{BASE}/control-health", headers=org["org_headers"]).status_code == 200
    assert client.get(f"{BASE}/risk-heatmap", headers=org["org_headers"]).status_code == 200
    assert client.get(f"{BASE}/recent-activity", headers=org["org_headers"]).status_code == 200

    after_count = db_session.query(AuditLog).filter(AuditLog.organization_id == org_uuid).count()
    assert after_count == before_count


def test_phase911_framework_readiness_per_active_framework(client):
    org = bootstrap_org_user(client, email_prefix="p911-frameworks")

    catalog = client.get("/api/v1/frameworks", headers=org["headers"])
    assert catalog.status_code == 200
    frameworks = catalog.json()
    assert len(frameworks) >= 2

    first_id = frameworks[0]["id"]
    second_id = frameworks[1]["id"]
    _activate_framework(client, org["org_headers"], first_id)
    _activate_framework(client, org["org_headers"], second_id)

    response = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 2

    ids = {row["framework_id"] for row in rows}
    assert first_id in ids
    assert second_id in ids

    required_fields = {
        "framework_id",
        "name",
        "coverage_level",
        "obligation_count",
        "mapped_control_count",
        "control_coverage_pct",
        "evidence_verified_pct",
        "open_gaps_count",
        "readiness_insight",
        "last_score_snapshot",
    }
    for row in rows:
        assert set(row.keys()) == required_fields
