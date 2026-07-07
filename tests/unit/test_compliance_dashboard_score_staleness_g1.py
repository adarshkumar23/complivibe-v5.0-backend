import uuid
from datetime import UTC, datetime, timedelta

from app.models.framework import Framework
from app.models.organization import Organization
from app.models.score_snapshot import ScoreSnapshot
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/dashboard"


def _activate_framework(client, headers: dict[str, str], framework_id: str) -> None:
    response = client.post(f"/api/v1/frameworks/{framework_id}/activate", headers=headers, json={"notes": "g1"})
    assert response.status_code == 200


def test_g1_framework_readiness_flags_stale_snapshot_and_underlying_change(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g1-stale")
    org_uuid = uuid.UUID(org["organization_id"])

    catalog = client.get("/api/v1/frameworks", headers=org["headers"])
    assert catalog.status_code == 200
    frameworks = catalog.json()
    assert frameworks
    framework_id = frameworks[0]["id"]
    _activate_framework(client, org["org_headers"], framework_id)

    # Insert an old score snapshot directly (simulating a snapshot calculated 90 days ago).
    old_calculated_at = datetime.now(UTC) - timedelta(days=90)
    snapshot = ScoreSnapshot(
        organization_id=org_uuid,
        snapshot_type="compliance_readiness",
        score=70,
        grade="C",
        inputs_json={},
        breakdown_json={},
        calculated_at=old_calculated_at,
    )
    db_session.add(snapshot)
    db_session.commit()

    response = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["last_score_snapshot"]["stale"] is True
    assert row["last_score_snapshot"]["age_hours"] > 24
    # No relevant audit log activity has occurred since the snapshot was calculated yet.
    assert row["last_score_snapshot"]["underlying_data_changed_since"] is False
    # readiness_insight synthesizes an explanation from real counts, not raw numbers only.
    assert isinstance(row["readiness_insight"], str) and len(row["readiness_insight"]) > 0

    # Now create a control, which writes a "control.created" audit log entry after the
    # snapshot's calculated_at -- the dashboard must flag that underlying data has moved on.
    control_response = client.post(
        "/api/v1/controls",
        headers=org["org_headers"],
        json={
            "title": "G1 Access Review Control",
            "control_type": "technical",
            "criticality": "medium",
        },
    )
    assert control_response.status_code == 201

    response_2 = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert response_2.status_code == 200
    row_2 = response_2.json()[0]
    assert row_2["last_score_snapshot"]["underlying_data_changed_since"] is True


def test_g1_framework_readiness_fresh_snapshot_not_flagged_stale(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g1-fresh")
    org_uuid = uuid.UUID(org["organization_id"])

    catalog = client.get("/api/v1/frameworks", headers=org["headers"])
    framework_id = catalog.json()[0]["id"]
    _activate_framework(client, org["org_headers"], framework_id)

    snapshot = ScoreSnapshot(
        organization_id=org_uuid,
        snapshot_type="compliance_readiness",
        score=85,
        grade="B",
        inputs_json={},
        breakdown_json={},
        calculated_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(snapshot)
    db_session.commit()

    response = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert response.status_code == 200
    row = response.json()[0]
    assert row["last_score_snapshot"]["stale"] is False
    assert row["last_score_snapshot"]["underlying_data_changed_since"] is False


def test_g1_framework_readiness_no_snapshot_yields_null(client):
    org = bootstrap_org_user(client, email_prefix="g1-nosnap")

    catalog = client.get("/api/v1/frameworks", headers=org["headers"])
    framework_id = catalog.json()[0]["id"]
    _activate_framework(client, org["org_headers"], framework_id)

    response = client.get(f"{BASE}/framework-readiness", headers=org["org_headers"])
    assert response.status_code == 200
    row = response.json()[0]
    assert row["last_score_snapshot"] is None
    # Seeded frameworks ship with real obligations but no control mappings for a brand new
    # org, so the insight should call out the gap using the real (non-zero) counts.
    assert row["obligation_count"] > 0
    assert row["open_gaps_count"] == row["obligation_count"]
    assert "have no mapped control" in row["readiness_insight"]
