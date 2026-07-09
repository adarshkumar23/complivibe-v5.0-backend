from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.control import Control
from app.models.evidence_automation_rule import EvidenceAutomationIngestEvent, EvidenceAutomationRule
from app.models.evidence_item import EvidenceItem


def _register(client, email: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!@", "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    response = client.get("/api/v1/organizations/me", headers=_headers(token))
    assert response.status_code == 200
    return response.json()[0]["id"]


def _create_control(client, token: str, org_id: str, title: str) -> str:
    response = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "technical", "criticality": "high"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_phase101_webhook_retry_is_deduped_by_idempotency_key(client, db_session):
    token = _register(client, "p101-owner-dedupe@example.com", "P101 Dedupe Org")
    org_id = _org_id(client, token)

    create_rule_response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "webhook",
            "trigger_config": {
                "match": {"event.kind": "deploy"},
                "required_fields": ["event.id"],
                "idempotency_key_path": "event.id",
            },
            "evidence_type": "technical_test",
            "transform_template": '{"title": "Deploy {{event.id}}"}',
        },
    )
    assert create_rule_response.status_code == 201, create_rule_response.text

    payload = {"payload": {"event": {"kind": "deploy", "id": "run-999"}}}

    first = client.post("/api/v1/evidence-automation/inbound/webhook", headers=_headers(token, org_id), json=payload)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["created_count"] == 1
    assert first_body["duplicate_count"] == 0

    # Simulate the webhook provider retrying the exact same delivery (e.g. because our
    # 200 response was lost in transit). This must not create a second evidence item.
    retry = client.post("/api/v1/evidence-automation/inbound/webhook", headers=_headers(token, org_id), json=payload)
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["created_count"] == 0
    assert retry_body["duplicate_count"] == 1
    assert retry_body["duplicates"][0]["idempotency_key"] == "run-999"

    evidence_rows = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == uuid.UUID(org_id))
        .all()
    )
    assert len(evidence_rows) == 1

    ingest_events = (
        db_session.query(EvidenceAutomationIngestEvent)
        .filter(EvidenceAutomationIngestEvent.organization_id == uuid.UUID(org_id))
        .all()
    )
    assert len(ingest_events) == 1
    assert ingest_events[0].idempotency_key == "run-999"
    assert ingest_events[0].status == "created"

    rule_row = db_session.query(EvidenceAutomationRule).filter(
        EvidenceAutomationRule.organization_id == uuid.UUID(org_id)
    ).one()
    assert rule_row.trigger_count == 1
    assert rule_row.last_triggered_at is not None
    assert rule_row.last_matched_at is not None


def test_phase101_ingest_without_idempotency_key_path_still_dedupes_by_content(client, db_session):
    """Even when a rule has no idempotency_key_path configured, byte-identical
    resubmissions of the same payload must not silently create disconnected evidence
    rows: create_evidence_item's checksum-based dedup (fingerprinted from the payload
    when the source doesn't supply an explicit checksum) is the fallback safety net."""
    token = _register(client, "p101-owner-nokey@example.com", "P101 NoKey Org")
    org_id = _org_id(client, token)

    client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "form",
            "trigger_config": {"required_fields": ["name"]},
            "evidence_type": "attestation",
            "transform_template": '{"title": "Attestation {{name}}"}',
        },
    )

    payload = {"payload": {"name": "quarterly-review"}}
    first = client.post("/api/v1/evidence-automation/inbound/form-submit", headers=_headers(token, org_id), json=payload)
    second = client.post("/api/v1/evidence-automation/inbound/form-submit", headers=_headers(token, org_id), json=payload)
    assert first.json()["created_count"] == 1
    assert second.json()["created_count"] == 0
    assert second.json()["duplicate_count"] == 1

    evidence_rows = db_session.query(EvidenceItem).filter(EvidenceItem.organization_id == uuid.UUID(org_id)).all()
    assert len(evidence_rows) == 1

    # A genuinely different payload (different content) is not deduped.
    other_payload = {"payload": {"name": "annual-review"}}
    third = client.post("/api/v1/evidence-automation/inbound/form-submit", headers=_headers(token, org_id), json=other_payload)
    assert third.json()["created_count"] == 1
    evidence_rows = db_session.query(EvidenceItem).filter(EvidenceItem.organization_id == uuid.UUID(org_id)).all()
    assert len(evidence_rows) == 2


def test_phase101_rule_read_surfaces_repeated_failure_and_archived_control_context(client, db_session):
    token = _register(client, "p101-owner-health@example.com", "P101 Health Org")
    org_id = _org_id(client, token)
    control_id = _create_control(client, token, org_id, "P101 control")

    create_rule_response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "webhook",
            "trigger_config": {"required_fields": ["event.id"], "match": {"event.kind": "bad"}},
            "target_control_id": control_id,
            "evidence_type": "technical_test",
            # The title template resolves to an empty string for every payload below
            # (the path never exists), so create_evidence_item's title-required check
            # raises on every matching delivery - each becomes a per-rule ingest error.
            "transform_template": '{"title": "{{missing.value}}"}',
        },
    )
    assert create_rule_response.status_code == 201
    rule_id = create_rule_response.json()["id"]

    for i in range(3):
        response = client.post(
            "/api/v1/evidence-automation/inbound/webhook",
            headers=_headers(token, org_id),
            json={"payload": {"event": {"kind": "bad", "id": f"evt-{i}"}}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["errors"], body

    # Archive the linked control out from under the rule.
    control_row = db_session.query(Control).filter(Control.id == uuid.UUID(control_id)).one()
    control_row.status = "archived"
    db_session.commit()

    detail = client.get("/api/v1/evidence-automation/rules", headers=_headers(token, org_id))
    assert detail.status_code == 200
    rule_body = next(row for row in detail.json() if row["id"] == rule_id)
    assert rule_body["consecutive_error_count"] >= 3
    assert rule_body["needs_attention"] is True
    assert "repeated_ingest_failures" in rule_body["context_flags"]
    assert rule_body["target_control_archived"] is True
    assert "target_control_archived" in rule_body["context_flags"]
    assert rule_body["last_error_message"]


def test_phase101_stale_connector_flagged_when_active_but_never_triggered(client, db_session):
    token = _register(client, "p101-owner-stale@example.com", "P101 Stale Org")
    org_id = _org_id(client, token)

    create_rule_response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "email",
            "trigger_config": {"required_fields": ["subject"]},
            "evidence_type": "attestation",
            "transform_template": '{"title": "Evidence {{subject}}"}',
        },
    )
    assert create_rule_response.status_code == 201
    rule_id = create_rule_response.json()["id"]

    # Backdate the rule's creation so it looks like it has existed for a while with
    # no successful trigger - this should be flagged as a stale/dark connector.
    rule_row = db_session.query(EvidenceAutomationRule).filter(
        EvidenceAutomationRule.id == uuid.UUID(rule_id)
    ).one()
    rule_row.created_at = datetime.now(UTC) - timedelta(days=30)
    db_session.commit()

    detail = client.get("/api/v1/evidence-automation/rules", headers=_headers(token, org_id))
    rule_body = next(row for row in detail.json() if row["id"] == rule_id)
    assert rule_body["is_stale"] is True
    assert "stale_connector" in rule_body["context_flags"]


def test_phase101_invalid_idempotency_key_path_rejected(client):
    token = _register(client, "p101-owner-invalid@example.com", "P101 Invalid Org")
    org_id = _org_id(client, token)

    response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "webhook",
            "trigger_config": {"idempotency_key_path": 123},
            "evidence_type": "other",
        },
    )
    assert response.status_code == 400
    assert "idempotency_key_path" in response.json()["detail"]
