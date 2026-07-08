from __future__ import annotations

import uuid

from app.models.external_sync_event import ExternalSyncEvent
from app.models.issue import Issue
from app.models.issue_sync_comment import IssueSyncComment
from app.models.user import User


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


def _user(db_session, email: str) -> User:
    return db_session.query(User).filter(User.email == email).one()


def _create_issue(client, token: str, org_id: str, owner_id: str) -> str:
    response = client.post(
        "/api/v1/compliance/issues",
        headers=_headers(token, org_id),
        json={
            "title": "P103 Linked Issue",
            "description": "Issue used for idempotency testing",
            "issue_type": "security_incident",
            "severity": "high",
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_phase103_jira_webhook_retry_with_same_timestamp_does_not_duplicate_comment(client, db_session):
    token = _register(client, "p103-owner-jira@example.com", "P103 Jira Org")
    org_id = _org_id(client, token)
    user = _user(db_session, "p103-owner-jira@example.com")
    issue_id = _create_issue(client, token, org_id, str(user.id))

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Jira Retry Test",
            "provider": "jira",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "api_base_url": "https://example.atlassian.net",
            "credentials_json": {"email": "bot@example.com", "api_token": "secret"},
            "webhook_secret": "shared-secret-123",
            "field_mapping_json": {"jira_status_to_internal": {"In Progress": "investigating"}},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = connection_response.json()["id"]

    link_response = client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/links",
        headers=_headers(token, org_id),
        json={"entity_type": "issue", "internal_entity_id": issue_id, "external_entity_id": "20001", "external_key": "P103-1"},
    )
    assert link_response.status_code == 201, link_response.text

    webhook_payload = {
        "webhookEvent": "jira:issue_updated",
        "timestamp": "1720000000000",
        "issue": {"id": "20001", "key": "P103-1", "fields": {"status": {"name": "In Progress"}}},
        "comment": {"id": "9101", "body": "Retried inbound note", "author": {"accountId": "jira-user-9"}},
    }

    first = client.post(
        f"/api/v1/issue-sync/webhooks/jira/{connection_id}",
        headers={**_headers(token, org_id), "X-Webhook-Secret": "shared-secret-123"},
        json=webhook_payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["duplicate_delivery"] is False
    first_event_id = first.json()["event_id"]

    # Jira retries the exact same delivery (identical timestamp = same event) because it
    # didn't see our 200 in time.
    retry = client.post(
        f"/api/v1/issue-sync/webhooks/jira/{connection_id}",
        headers={**_headers(token, org_id), "X-Webhook-Secret": "shared-secret-123"},
        json=webhook_payload,
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicate_delivery"] is True
    assert retry.json()["event_id"] == first_event_id

    db_session.expire_all()
    comments = (
        db_session.query(IssueSyncComment)
        .filter(
            IssueSyncComment.organization_id == uuid.UUID(org_id),
            IssueSyncComment.issue_id == uuid.UUID(issue_id),
            IssueSyncComment.direction == "inbound",
        )
        .all()
    )
    assert len(comments) == 1

    events = (
        db_session.query(ExternalSyncEvent)
        .filter(
            ExternalSyncEvent.organization_id == uuid.UUID(org_id),
            ExternalSyncEvent.connection_id == uuid.UUID(connection_id),
            ExternalSyncEvent.direction == "inbound",
        )
        .all()
    )
    assert len(events) == 1


def test_phase103_different_external_event_id_is_processed_independently(client, db_session):
    token = _register(client, "p103-owner-distinct@example.com", "P103 Distinct Org")
    org_id = _org_id(client, token)
    user = _user(db_session, "p103-owner-distinct@example.com")
    issue_id = _create_issue(client, token, org_id, str(user.id))

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Jira Distinct Test",
            "provider": "jira",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "api_base_url": "https://example.atlassian.net",
            "credentials_json": {"email": "bot@example.com", "api_token": "secret"},
        },
    )
    connection_id = connection_response.json()["id"]

    client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/links",
        headers=_headers(token, org_id),
        json={"entity_type": "issue", "internal_entity_id": issue_id, "external_entity_id": "20002"},
    )

    for i, ts in enumerate(["1720000001000", "1720000002000"]):
        response = client.post(
            f"/api/v1/issue-sync/webhooks/jira/{connection_id}",
            headers=_headers(token, org_id),
            json={
                "webhookEvent": "jira:issue_updated",
                "timestamp": ts,
                "issue": {"id": "20002", "fields": {"status": {}}},
                "comment": {"id": f"c-{i}", "body": f"note {i}", "author": {}},
            },
        )
        assert response.status_code == 200
        assert response.json()["duplicate_delivery"] is False

    events = (
        db_session.query(ExternalSyncEvent)
        .filter(ExternalSyncEvent.organization_id == uuid.UUID(org_id), ExternalSyncEvent.connection_id == uuid.UUID(connection_id))
        .all()
    )
    assert len(events) == 2


def test_phase103_connection_flags_unauthenticated_inbound_webhook(client, db_session):
    token = _register(client, "p103-owner-noauth@example.com", "P103 NoAuth Org")
    org_id = _org_id(client, token)

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Linear No Secret",
            "provider": "linear",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "credentials_json": {"api_key": "linear-key"},
        },
    )
    assert connection_response.status_code == 201
    body = connection_response.json()
    assert "webhook_unauthenticated" in body["context_flags"]

    with_secret = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Linear With Secret",
            "provider": "linear",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "credentials_json": {"api_key": "linear-key"},
            "webhook_secret": "sekret",
        },
    )
    assert with_secret.status_code == 201
    assert "webhook_unauthenticated" not in with_secret.json()["context_flags"]

    outbound_only = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Linear Outbound Only",
            "provider": "linear",
            "entity_type": "issue",
            "direction_mode": "outbound_only",
            "credentials_json": {"api_key": "linear-key"},
        },
    )
    assert outbound_only.status_code == 201
    # No inbound webhook is exposed for outbound_only, so there's nothing to authenticate.
    assert "webhook_unauthenticated" not in outbound_only.json()["context_flags"]


def test_g9_linear_webhook_dedups_on_real_webhookid_not_id_or_eventid(client, db_session):
    """G9 item 7: real Linear webhook deliveries carry their delivery identifier in a
    top-level `webhookId` field -- not `id`/`eventId` (those don't exist at the top
    level of a genuine Linear payload). A replayed delivery must be deduped."""
    token = _register(client, "g9-linear-webhookid@example.com", "G9 Linear WebhookId Org")
    org_id = _org_id(client, token)

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Linear WebhookId Test",
            "provider": "linear",
            "entity_type": "issue",
            "direction_mode": "inbound_only",
            "credentials_json": {"api_key": "linear-key"},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = connection_response.json()["id"]

    payload = {
        "action": "update",
        "type": "Issue",
        "createdAt": "2026-07-08T18:00:00.000Z",
        "data": {"id": "issue-uuid-abc", "identifier": "ENG-42", "state": {"name": "In Progress"}},
        "url": "https://linear.app/x/issue/ENG-42",
        "organizationId": "org-abc",
        "webhookTimestamp": 1783533600000,
        "webhookId": "webhook-real-delivery-id-999",
    }

    first = client.post(
        f"/api/v1/issue-sync/webhooks/linear/{connection_id}",
        headers=_headers(token, org_id),
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["duplicate_delivery"] is False

    replay = client.post(
        f"/api/v1/issue-sync/webhooks/linear/{connection_id}",
        headers=_headers(token, org_id),
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["duplicate_delivery"] is True
    assert replay.json()["event_id"] == first.json()["event_id"]

    events = (
        db_session.query(ExternalSyncEvent)
        .filter(ExternalSyncEvent.organization_id == uuid.UUID(org_id), ExternalSyncEvent.connection_id == uuid.UUID(connection_id))
        .all()
    )
    assert len(events) == 1


def test_g9_jira_same_timestamp_different_deliveries_not_merged(client, db_session):
    """G9 item 7: two genuinely DIFFERENT Jira deliveries that happen to share a
    `timestamp` value must NOT be treated as duplicates of each other -- only a
    true replay (identical comment) should dedup."""
    token = _register(client, "g9-jira-timestamp@example.com", "G9 Jira Timestamp Org")
    org_id = _org_id(client, token)
    user = _user(db_session, "g9-jira-timestamp@example.com")
    issue_id = _create_issue(client, token, org_id, str(user.id))

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Jira Timestamp Collision Test",
            "provider": "jira",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "api_base_url": "https://example.atlassian.net",
            "credentials_json": {"email": "bot@example.com", "api_token": "secret"},
        },
    )
    connection_id = connection_response.json()["id"]

    client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/links",
        headers=_headers(token, org_id),
        json={"entity_type": "issue", "internal_entity_id": issue_id, "external_entity_id": "30001", "external_key": "G9-1"},
    )

    shared_timestamp = "1783533600000"
    payload_a = {
        "webhookEvent": "jira:issue_updated",
        "timestamp": shared_timestamp,
        "issue": {"id": "30001", "key": "G9-1", "fields": {"status": {"name": "In Progress"}}},
        "comment": {"id": "9001", "body": "First comment", "author": {"accountId": "jira-user-1"}},
    }
    payload_b = {
        "webhookEvent": "jira:issue_updated",
        "timestamp": shared_timestamp,
        "issue": {"id": "30001", "key": "G9-1", "fields": {"status": {"name": "Done"}}},
        "comment": {"id": "9002", "body": "Second, genuinely different comment", "author": {"accountId": "jira-user-2"}},
    }

    response_a = client.post(f"/api/v1/issue-sync/webhooks/jira/{connection_id}", headers=_headers(token, org_id), json=payload_a)
    response_b = client.post(f"/api/v1/issue-sync/webhooks/jira/{connection_id}", headers=_headers(token, org_id), json=payload_b)
    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert response_a.json()["duplicate_delivery"] is False
    assert response_b.json()["duplicate_delivery"] is False
    assert response_a.json()["event_id"] != response_b.json()["event_id"]

    # A true replay of A must still be recognized as a duplicate.
    replay_a = client.post(f"/api/v1/issue-sync/webhooks/jira/{connection_id}", headers=_headers(token, org_id), json=payload_a)
    assert replay_a.status_code == 200
    assert replay_a.json()["duplicate_delivery"] is True
    assert replay_a.json()["event_id"] == response_a.json()["event_id"]

    events = (
        db_session.query(ExternalSyncEvent)
        .filter(ExternalSyncEvent.organization_id == uuid.UUID(org_id), ExternalSyncEvent.connection_id == uuid.UUID(connection_id))
        .all()
    )
    assert len(events) == 2
