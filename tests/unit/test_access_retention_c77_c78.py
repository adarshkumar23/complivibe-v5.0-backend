from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models.data_access_log import DataAccessLog
from app.models.data_asset import DataAsset
from app.models.data_retention_review import DataRetentionReview
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
LINEAGE_BASE = "/api/v1/data-observability/lineage"
ACCESS_BASE = "/api/v1/data-observability/access"
RETENTION_BASE = "/api/v1/data-observability/retention"


def _create_asset(client, headers: dict[str, str], owner_id: str, *, name: str) -> str:
    response = client.post(
        ASSETS_BASE,
        headers=headers,
        json={
            "name": name,
            "asset_type": "table",
            "owner_id": owner_id,
            "description": "Asset for access and retention tests",
            "schema_column_names": ["customer_id", "email"],
            "permitted_regions": ["US"],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _configure_ingest_key(client, headers: dict[str, str], api_key: str | None = None) -> str:
    # Access-monitoring has its OWN key now (key_type "access_monitoring"), decoupled
    # from the shared OpenMetadata/lineage key. Returns the provisioned key to use.
    response = client.post(
        "/api/v1/integrations/ingest-keys",
        headers=headers,
        json={"key_type": "access_monitoring"},
    )
    assert response.status_code == 201, response.text
    return response.json()["api_key"]


def _ingest_event(
    client,
    api_key: str,
    *,
    asset_id: str,
    access_type: str,
    access_result: str,
    access_time: datetime,
    actor_id: str | None = None,
    source_country: str | None = "US",
    bytes_transferred: int | None = None,
    actor_external: str | None = None,
) -> dict:
    payload = {
        "data_asset_id": asset_id,
        "access_type": access_type,
        "access_result": access_result,
        "access_time": access_time.isoformat(),
        "source_country": source_country,
        "bytes_transferred": bytes_transferred,
        "actor_id": actor_id,
        "actor_external": actor_external,
        "metadata": {"source": "unit-test"},
    }
    response = client.post(
        f"{ACCESS_BASE}/events",
        headers={"X-CompliVibe-Key": api_key},
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def test_c77_data_access_monitoring(client):
    org = bootstrap_org_user(client, email_prefix="c77-org")
    ingest_key = _configure_ingest_key(client, org["org_headers"])

    spike_asset_id = _create_asset(client, org["org_headers"], org["user_id"], name="c77_spike_asset")
    actor_asset_id = _create_asset(client, org["org_headers"], org["user_id"], name="c77_actor_asset")
    compliant_asset_id = _create_asset(client, org["org_headers"], org["user_id"], name="c77_compliant_asset")

    at_noon = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    # access_count_spike default rule: 100 in 10 minutes; 101st breaches.
    for _ in range(101):
        _ingest_event(
            client,
            ingest_key,
            asset_id=spike_asset_id,
            access_type="read",
            access_result="success",
            access_time=at_noon,
            actor_id=org["user_id"],
            source_country="US",
        )

    # after_hours_access default rule.
    _ingest_event(
        client,
        ingest_key,
        asset_id=spike_asset_id,
        access_type="query",
        access_result="success",
        access_time=datetime(2026, 6, 26, 23, 0, tzinfo=UTC),
        actor_id=org["user_id"],
        source_country="US",
    )

    # new_actor_access custom rule.
    new_actor_rule = client.post(
        f"{ACCESS_BASE}/anomaly-rules",
        headers=org["org_headers"],
        json={
            "data_asset_id": actor_asset_id,
            "rule_type": "new_actor_access",
            "rule_config": {},
        },
    )
    assert new_actor_rule.status_code == 201
    _ingest_event(
        client,
        ingest_key,
        asset_id=actor_asset_id,
        access_type="read",
        access_result="success",
        access_time=at_noon,
        actor_id=org["user_id"],
        source_country="US",
    )

    # mass_download default rule (5GB).
    _ingest_event(
        client,
        ingest_key,
        asset_id=spike_asset_id,
        access_type="export",
        access_result="success",
        access_time=at_noon,
        actor_id=org["user_id"],
        source_country="US",
        bytes_transferred=6_000_000_000,
    )

    # failed_access_spike default rule: 20 in 5 minutes.
    for _ in range(21):
        _ingest_event(
            client,
            ingest_key,
            asset_id=spike_asset_id,
            access_type="query",
            access_result="failed",
            access_time=at_noon,
            actor_id=org["user_id"],
            source_country="US",
        )

    # cross_border_access custom rule.
    cross_border_rule = client.post(
        f"{ACCESS_BASE}/anomaly-rules",
        headers=org["org_headers"],
        json={
            "data_asset_id": compliant_asset_id,
            "rule_type": "cross_border_access",
            "rule_config": {},
        },
    )
    assert cross_border_rule.status_code == 201
    cross_border_event = _ingest_event(
        client,
        ingest_key,
        asset_id=compliant_asset_id,
        access_type="read",
        access_result="success",
        access_time=at_noon,
        actor_id=org["user_id"],
        source_country="IN",
    )
    assert cross_border_event["risk_level"] in {"medium", "high"}
    assert "cross_border_region_mismatch" in cross_border_event["context_flags"]

    # Compliant event should not add anomalies for this asset.
    before = client.get(
        f"{ACCESS_BASE}/summary?data_asset_id={compliant_asset_id}",
        headers=org["org_headers"],
    )
    assert before.status_code == 200
    before_anomalies = before.json()["anomalies_detected"]

    _ingest_event(
        client,
        ingest_key,
        asset_id=compliant_asset_id,
        access_type="read",
        access_result="success",
        access_time=at_noon + timedelta(minutes=1),
        actor_id=org["user_id"],
        source_country="US",
    )

    after = client.get(
        f"{ACCESS_BASE}/summary?data_asset_id={compliant_asset_id}",
        headers=org["org_headers"],
    )
    assert after.status_code == 200
    assert after.json()["anomalies_detected"] == before_anomalies
    assert "failed_access_rate" in after.json()
    assert "anomalous_access_rate" in after.json()
    assert "context_flags" in after.json()

    # Time-range filtered logs.
    _ingest_event(
        client,
        ingest_key,
        asset_id=compliant_asset_id,
        access_type="read",
        access_result="success",
        access_time=at_noon - timedelta(days=2),
        actor_id=org["user_id"],
        source_country="US",
    )
    ranged = client.get(
        f"{ACCESS_BASE}/logs",
        headers=org["org_headers"],
        params={
            "data_asset_id": compliant_asset_id,
            "from_time": (at_noon - timedelta(hours=1)).isoformat(),
            "to_time": (at_noon + timedelta(hours=2)).isoformat(),
        },
    )
    assert ranged.status_code == 200
    from_time = at_noon - timedelta(hours=1)
    to_time = at_noon + timedelta(hours=2)
    for row in ranged.json():
        access_ts = datetime.fromisoformat(row["access_time"].replace("Z", "+00:00"))
        if access_ts.tzinfo is None:
            access_ts = access_ts.replace(tzinfo=UTC)
        assert from_time <= access_ts <= to_time
        assert "risk_level" in row
        assert "context_flags" in row

    source = Path("app/data_observability/services/access_monitoring_service.py").read_text(encoding="utf-8")
    assert "delete(DataAccessLog" not in source
    assert "self.db.delete(row)" not in source

    # Asset-scoped endpoint works.
    asset_logs = client.get(f"{ASSETS_BASE}/{compliant_asset_id}/access-logs", headers=org["org_headers"])
    assert asset_logs.status_code == 200
    assert len(asset_logs.json()) >= 1
    assert "risk_score" in asset_logs.json()[0]

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="c77-org-b")
    forbidden = client.get(f"{ACCESS_BASE}/logs?data_asset_id={spike_asset_id}", headers=org_b["org_headers"])
    assert forbidden.status_code == 200
    assert forbidden.json() == []

    # Duplicate active anomaly rule for same scope should be rejected.
    duplicate_rule = client.post(
        f"{ACCESS_BASE}/anomaly-rules",
        headers=org["org_headers"],
        json={
            "data_asset_id": compliant_asset_id,
            "rule_type": "cross_border_access",
            "rule_config": {},
        },
    )
    assert duplicate_rule.status_code == 409

    # List anomaly rules includes context and hit metrics.
    listed_rules = client.get(f"{ACCESS_BASE}/anomaly-rules", headers=org["org_headers"])
    assert listed_rules.status_code == 200
    assert any("hit_count_7d" in row for row in listed_rules.json())
    assert any("context_flags" in row for row in listed_rules.json())

    # Invalid time window is rejected.
    invalid_window = client.get(
        f"{ACCESS_BASE}/logs",
        headers=org["org_headers"],
        params={"from_time": (at_noon + timedelta(hours=2)).isoformat(), "to_time": (at_noon - timedelta(hours=1)).isoformat()},
    )
    assert invalid_window.status_code == 422


def test_c77_ingest_rejects_cross_tenant_actor_id(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="c77-actor-a")
    org_b = bootstrap_org_user(client, email_prefix="c77-actor-b")
    ingest_key = _configure_ingest_key(client, org_a["org_headers"])
    asset_id = _create_asset(client, org_a["org_headers"], org_a["user_id"], name="c77_cross_actor_asset")

    response = client.post(
        f"{ACCESS_BASE}/events",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "data_asset_id": asset_id,
            "actor_id": org_b["user_id"],
            "access_type": "read",
            "access_result": "success",
            "access_time": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 422
    assert "actor_id" in response.json()["detail"]

    persisted = (
        db_session.query(DataAccessLog)
        .filter(
            DataAccessLog.organization_id == uuid.UUID(org_a["organization_id"]),
            DataAccessLog.actor_id == uuid.UUID(org_b["user_id"]),
        )
        .count()
    )
    assert persisted == 0


def test_c77_ingest_rejects_ambiguous_actor_and_negative_metrics(client):
    org = bootstrap_org_user(client, email_prefix="c77-ambiguous")
    ingest_key = _configure_ingest_key(client, org["org_headers"])
    asset_id = _create_asset(client, org["org_headers"], org["user_id"], name="c77_ambiguous_asset")

    ambiguous_actor = client.post(
        f"{ACCESS_BASE}/events",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "data_asset_id": asset_id,
            "actor_id": org["user_id"],
            "actor_external": "etl-service",
            "access_type": "read",
            "access_result": "success",
            "access_time": datetime.now(UTC).isoformat(),
        },
    )
    assert ambiguous_actor.status_code == 422

    negative_metrics = client.post(
        f"{ACCESS_BASE}/events",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "data_asset_id": asset_id,
            "actor_id": org["user_id"],
            "access_type": "read",
            "access_result": "success",
            "access_time": datetime.now(UTC).isoformat(),
            "bytes_transferred": -1,
        },
    )
    assert negative_metrics.status_code == 422


def test_c78_retention_policy_enforcement(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c78-org")

    asset_1 = _create_asset(client, org["org_headers"], org["user_id"], name="c78_asset_expired")
    asset_2 = _create_asset(client, org["org_headers"], org["user_id"], name="c78_asset_active")
    asset_3 = _create_asset(client, org["org_headers"], org["user_id"], name="c78_asset_waive")

    created_policy = client.post(
        f"{RETENTION_BASE}/policies",
        headers=org["org_headers"],
        json={
            "name": "Default retention policy",
            "description": "30 day retention",
            "retention_days": 30,
            "action_on_expiry": "flag",
        },
    )
    assert created_policy.status_code == 201
    policy_id = created_policy.json()["id"]

    for asset_id in (asset_1, asset_2, asset_3):
        applied = client.post(
            f"{RETENTION_BASE}/policies/{policy_id}/apply-to-asset",
            headers=org["org_headers"],
            json={"data_asset_id": asset_id},
        )
        assert applied.status_code == 200
        assert applied.json()["retention_policy_days"] == 30

    # The sweep is driven by retention_review_date (the field actually exposed for editing
    # via the asset API, auto-set by apply-to-asset above) rather than created_at, so
    # backdate that instead of created_at to simulate an overdue/upcoming review.
    now = datetime.now(UTC)
    old_review_date = (now - timedelta(days=15)).date()
    upcoming_review_date = (now + timedelta(days=20)).date()

    for asset_id, review_date in ((asset_1, old_review_date), (asset_2, upcoming_review_date), (asset_3, old_review_date)):
        row = db_session.get(DataAsset, uuid.UUID(asset_id))
        assert row is not None
        row.retention_review_date = review_date
    db_session.commit()

    sweep_1 = client.post(f"{RETENTION_BASE}/trigger-sweep", headers=org["org_headers"])
    assert sweep_1.status_code == 200
    assert sweep_1.json()["assets_flagged"] >= 2
    assert sweep_1.json()["tasks_created"] >= 2

    pending = client.get(f"{RETENTION_BASE}/reviews?status=pending", headers=org["org_headers"])
    assert pending.status_code == 200
    pending_rows = pending.json()
    assert len(pending_rows) >= 2

    first_review = next(row for row in pending_rows if row["data_asset_id"] == asset_1)
    assert first_review["linked_task_id"] is not None
    task = db_session.get(Task, uuid.UUID(first_review["linked_task_id"]))
    assert task is not None

    sweep_2 = client.post(f"{RETENTION_BASE}/trigger-sweep", headers=org["org_headers"])
    assert sweep_2.status_code == 200
    # Idempotent for pending reviews.
    pending_again = client.get(f"{RETENTION_BASE}/reviews?status=pending", headers=org["org_headers"])
    assert pending_again.status_code == 200
    assert len(pending_again.json()) == len(pending_rows)

    resolved = client.post(
        f"{RETENTION_BASE}/reviews/{first_review['id']}/resolve",
        headers=org["org_headers"],
        json={"evidence_notes": "Asset archived in source system"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "completed"

    waive_target = next(row for row in pending_again.json() if row["data_asset_id"] == asset_3)
    waived = client.post(
        f"{RETENTION_BASE}/reviews/{waive_target['id']}/waive",
        headers=org["org_headers"],
        json={"reason": "Legal hold extension"},
    )
    assert waived.status_code == 200
    assert waived.json()["status"] == "waived"

    summary = client.get(f"{RETENTION_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_assets_with_policy"] == 3
    # asset_1 was resolved above: resolving must push retention_review_date out to
    # today + retention_days (G3 fix), not leave it (or reset it to) today/the old
    # overdue date -- otherwise it would immediately be re-flagged as still
    # "expired" by the very next sweep/summary, an infinite reflagging loop. Only
    # asset_3 (waived, not resolved -- its date is intentionally untouched) is
    # still expired here.
    assert body["expired_count"] == 1
    assert 0.0 <= float(body["compliance_rate"]) <= 100.0

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="c78-org-b")
    forbidden = client.post(
        f"{RETENTION_BASE}/reviews/{first_review['id']}/resolve",
        headers=org_b["org_headers"],
        json={"evidence_notes": "not allowed"},
    )
    assert forbidden.status_code == 404

    # Ensure at least one persisted review for this org.
    persisted_count = (
        db_session.query(DataRetentionReview)
        .filter(DataRetentionReview.organization_id == uuid.UUID(org["organization_id"]))
        .count()
    )
    assert persisted_count >= 2
