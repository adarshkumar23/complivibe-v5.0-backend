from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.data_quality_reading import DataQualityReading
from tests.helpers.auth_org import bootstrap_org_user

DASHBOARD_BASE = "/api/v1/data-observability/dashboard"
ASSETS_BASE = "/api/v1/data-observability/assets"
QUALITY_BASE = "/api/v1/data-observability/quality"


def test_g1_empty_org_dashboard_insight_says_no_assets(client):
    org = bootstrap_org_user(client, email_prefix="dobs-empty")
    resp = client.get(DASHBOARD_BASE, headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["insights"] == ["No data assets have been registered yet."]


def test_g1_dashboard_insights_and_breach_rate_aggregate_correctly_at_volume(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dobs-volume")
    org_id = uuid.UUID(org["organization_id"])

    create_resp = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "Volume asset",
            "asset_type": "table",
            "owner_id": org["user_id"],
            "description": "asset for volume test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    asset_id = uuid.UUID(create_resp.json()["id"])

    config_resp = client.post(
        f"{QUALITY_BASE}/configs",
        headers=org["org_headers"],
        json={
            "data_asset_id": str(asset_id),
            "metric_type": "freshness",
            "threshold_value": 0.95,
            "comparison_direction": "below",
            "alert_on_breach": True,
            "measurement_frequency": "daily",
        },
    )
    assert config_resp.status_code == 201, config_resp.text
    config_id = uuid.UUID(config_resp.json()["id"])

    # Simulate a large volume of readings (well beyond a small in-memory-friendly sample) to
    # exercise the SQL-side aggregate path rather than a Python loop over every row.
    now = datetime.now(UTC)
    total_readings = 250
    breach_readings = 60
    for i in range(total_readings):
        db_session.add(
            DataQualityReading(
                organization_id=org_id,
                config_id=config_id,
                value=Decimal("1.10") if i < breach_readings else Decimal("0.50"),
                reading_source="api_report",
                source_tool="test",
                within_threshold=not (i < breach_readings),
                created_at=now,
            )
        )
    db_session.commit()

    resp = client.get(DASHBOARD_BASE, headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()

    assert body["quality_metrics"]["readings_last_7d"] == total_readings
    assert body["quality_metrics"]["breach_count_7d"] == breach_readings
    assert body["quality_metrics"]["pass_count_7d"] == total_readings - breach_readings
    expected_rate = round(breach_readings / total_readings * 100.0, 1)
    assert round(body["quality_metrics"]["breach_rate_7d"], 1) == expected_rate

    insights = body["insights"]
    assert any("need classification review" in item for item in insights)
    assert any("breached their threshold" in item for item in insights)
