from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from tests.helpers.auth_org import bootstrap_org_user


def _seed_audit(db_session, org_id: str, action: str, minute_offset: int) -> AuditLog:
    ts = datetime.now(UTC) + timedelta(minutes=minute_offset)
    row = AuditLog(
        organization_id=UUID(org_id),
        action=action,
        entity_type="unit_test",
        entity_id=None,
        actor_user_id=None,
        before_json={},
        after_json={},
        metadata_json={"seeded": True},
        created_at=ts,
        updated_at=ts,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _enable_siem_feature(db_session, organization_id: str) -> None:
    org = db_session.get(Organization, UUID(organization_id))
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = "growth"
    db_session.commit()


class _PushSuccessResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None


def test_siem_export_endpoints_and_formats(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="siem-a")
    org_b = bootstrap_org_user(client, email_prefix="siem-b")
    _enable_siem_feature(db_session, org["organization_id"])
    _enable_siem_feature(db_session, org_b["organization_id"])

    tables = set(inspect(db_session.bind).get_table_names())
    assert "siem_export_configs" in tables
    assert "siem_export_runs" in tables

    pushed_calls: list[dict] = []

    def _fake_post(url, **kwargs):
        pushed_calls.append({"url": url, **kwargs})
        return _PushSuccessResponse()

    monkeypatch.setattr("httpx.post", _fake_post)

    create_resp = client.post(
        "/api/v1/siem/config",
        headers=org["org_headers"],
        json={
            "export_format": "json",
            "delivery_method": "webhook",
            "endpoint_url": "https://example.com/ingest",
            "api_key": "super-secret-key",
            "batch_size": 50,
        },
    )
    assert create_resp.status_code == 201

    get_resp = client.get("/api/v1/siem/config", headers=org["org_headers"])
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["export_format"] == "json"
    assert "api_key_hash" not in body

    duplicate = client.post("/api/v1/siem/config", headers=org["org_headers"], json={})
    assert duplicate.status_code == 409

    _seed_audit(db_session, org["organization_id"], "siem.action.one", 1)
    _seed_audit(db_session, org["organization_id"], "siem.action.two", 2)

    activate = client.post("/api/v1/siem/config/activate", headers=org["org_headers"])
    assert activate.status_code == 200
    assert activate.json()["is_active"] is True

    export_json = client.post("/api/v1/siem/export", headers=org["org_headers"], json={"limit": 10})
    assert export_json.status_code == 200
    assert export_json.json()["records"] >= 2
    assert isinstance(export_json.json()["payload"], list)
    # Config has delivery_method="webhook" + an endpoint_url, so export_batch must have
    # actually pushed the batch via HTTP POST, not just returned it for pull.
    assert export_json.json()["push_delivered"] is True
    assert export_json.json()["push_error"] is None
    assert pushed_calls
    assert pushed_calls[-1]["url"] == "https://example.com/ingest"
    assert pushed_calls[-1]["json"] == export_json.json()["payload"]

    switch_cef = client.patch("/api/v1/siem/config", headers=org["org_headers"], json={"export_format": "cef"})
    assert switch_cef.status_code == 200
    export_cef = client.post("/api/v1/siem/export", headers=org["org_headers"], json={"limit": 10})
    assert export_cef.status_code == 200
    assert isinstance(export_cef.json()["payload"], str)
    assert "CEF:" in export_cef.json()["payload"]

    switch_hec = client.patch("/api/v1/siem/config", headers=org["org_headers"], json={"export_format": "splunk_hec"})
    assert switch_hec.status_code == 200
    export_hec = client.post("/api/v1/siem/export", headers=org["org_headers"], json={"limit": 10})
    assert export_hec.status_code == 200
    hec_payload = export_hec.json()["payload"]
    assert isinstance(hec_payload, list)
    assert hec_payload
    assert "time" in hec_payload[0]
    assert "event" in hec_payload[0]

    preview = client.get("/api/v1/siem/export/preview", headers=org["org_headers"])
    assert preview.status_code == 200
    assert preview.json()["records"] <= 10

    runs = client.get("/api/v1/siem/export/runs", headers=org["org_headers"])
    assert runs.status_code == 200
    assert runs.json()

    deactivate = client.post("/api/v1/siem/config/deactivate", headers=org["org_headers"])
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    inactive_export = client.post("/api/v1/siem/export", headers=org["org_headers"], json={"limit": 10})
    assert inactive_export.status_code == 400

    not_visible_other_org = client.get("/api/v1/siem/config", headers=org_b["org_headers"])
    assert not_visible_other_org.status_code == 404


def test_siem_cursor_pagination_and_audit_and_admin_gate(client, db_session):
    org = bootstrap_org_user(client, email_prefix="siem-cursor")
    outsider = bootstrap_org_user(client, email_prefix="siem-outsider")
    _enable_siem_feature(db_session, org["organization_id"])
    _enable_siem_feature(db_session, outsider["organization_id"])

    create = client.post(
        "/api/v1/siem/config",
        headers=org["org_headers"],
        # api_pull: this test only exercises cursor pagination over the pull endpoint, so
        # no endpoint_url is needed (delivery_method="webhook" would require one).
        json={"export_format": "json", "delivery_method": "api_pull", "batch_size": 2},
    )
    assert create.status_code == 201

    created_log = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "siem_config.created",
        )
    ).scalar_one_or_none()
    assert created_log is not None

    activate = client.post("/api/v1/siem/config/activate", headers=org["org_headers"])
    assert activate.status_code == 200

    first = _seed_audit(db_session, org["organization_id"], "cursor.a", 1)
    _seed_audit(db_session, org["organization_id"], "cursor.b", 2)
    _seed_audit(db_session, org["organization_id"], "cursor.c", 3)

    page = client.post(
        "/api/v1/siem/export",
        headers=org["org_headers"],
        json={"limit": 10, "since_id": str(first.id)},
    )
    assert page.status_code == 200
    payload = page.json()["payload"]
    assert isinstance(payload, list)
    assert payload
    assert all(item["action"] in {"cursor.b", "cursor.c", "siem_config.created", "siem_config.activated"} for item in payload)

    no_admin = client.post("/api/v1/siem/config", headers=org["org_headers"] | outsider["headers"], json={})
    assert no_admin.status_code == 403

    delete_resp = client.delete("/api/v1/siem/config", headers=org["org_headers"])
    assert delete_resp.status_code == 204


def test_siem_push_requires_endpoint_url_and_rejects_unimplemented_methods(client, db_session):
    org = bootstrap_org_user(client, email_prefix="siem-push-validate")
    _enable_siem_feature(db_session, org["organization_id"])

    # delivery_method="webhook" (the default) with no endpoint_url must be rejected up
    # front rather than silently accepted and then never delivering.
    missing_endpoint = client.post(
        "/api/v1/siem/config",
        headers=org["org_headers"],
        json={"delivery_method": "webhook"},
    )
    assert missing_endpoint.status_code == 422

    # delivery_method values the platform doesn't actually implement push transport for
    # yet must be rejected clearly instead of silently no-op'ing.
    unimplemented = client.post(
        "/api/v1/siem/config",
        headers=org["org_headers"],
        json={"delivery_method": "syslog"},
    )
    assert unimplemented.status_code == 422
    assert "not yet implemented" in unimplemented.json()["detail"]


def test_siem_push_failure_is_recorded_and_counted(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="siem-push-fail")
    _enable_siem_feature(db_session, org["organization_id"])

    def _fake_post(url, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr("httpx.post", _fake_post)

    create = client.post(
        "/api/v1/siem/config",
        headers=org["org_headers"],
        json={"delivery_method": "webhook", "endpoint_url": "https://example.com/ingest"},
    )
    assert create.status_code == 201

    client.post("/api/v1/siem/config/activate", headers=org["org_headers"])
    _seed_audit(db_session, org["organization_id"], "siem.push.fail.one", 1)

    export_resp = client.post("/api/v1/siem/export", headers=org["org_headers"], json={"limit": 10})
    assert export_resp.status_code == 200
    body = export_resp.json()
    assert body["push_delivered"] is False
    assert "connection refused" in body["push_error"]

    config = client.get("/api/v1/siem/config", headers=org["org_headers"]).json()
    assert config["export_failures"] == 1

    runs = client.get("/api/v1/siem/export/runs", headers=org["org_headers"]).json()
    assert runs[0]["status"] == "partial"
    assert "connection refused" in runs[0]["error_message"]
