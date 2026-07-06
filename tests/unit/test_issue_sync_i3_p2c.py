import uuid

from app.models.audit_log import AuditLog
from app.models.external_sync_event import ExternalSyncEvent
from app.models.issue import Issue
from app.models.issue_sync_comment import IssueSyncComment
from app.models.user import User
from app.services.issue_sync_service import IssueSyncService


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
            "title": "I3 Linked Issue",
            "description": "Issue used for sync testing",
            "issue_type": "security_incident",
            "severity": "high",
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_i3_jira_two_way_status_and_comment_sync(client, db_session, monkeypatch):
    token = _register(client, "i3-owner-a@example.com", "I3 Org A")
    org_id = _org_id(client, token)
    user = _user(db_session, "i3-owner-a@example.com")
    issue_id = _create_issue(client, token, org_id, str(user.id))

    called = {"jira": 0}

    def _fake_send_outbound_jira(self, **kwargs):  # noqa: ANN001
        called["jira"] += 1
        return {"provider": "jira", "external_status": "To Do"}

    monkeypatch.setattr(IssueSyncService, "_send_outbound_jira", _fake_send_outbound_jira)

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Jira Security",
            "provider": "jira",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "api_base_url": "https://example.atlassian.net",
            "credentials_json": {"email": "bot@example.com", "api_token": "secret"},
            "field_mapping_json": {
                "internal_to_jira_status": {"open": "To Do", "investigating": "In Progress"},
                "jira_status_to_internal": {"In Progress": "investigating"},
            },
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = connection_response.json()["id"]

    link_response = client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/links",
        headers=_headers(token, org_id),
        json={
            "entity_type": "issue",
            "internal_entity_id": issue_id,
            "external_entity_id": "10001",
            "external_key": "CPL-10001",
        },
    )
    assert link_response.status_code == 201, link_response.text

    outbound_response = client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/sync/outbound",
        headers=_headers(token, org_id),
        json={"issue_id": issue_id, "include_status": True, "include_comment": True, "comment_body": "Outbound note"},
    )
    assert outbound_response.status_code == 200, outbound_response.text
    assert outbound_response.json()["status"] == "processed"
    assert called["jira"] == 1

    inbound_response = client.post(
        f"/api/v1/issue-sync/webhooks/jira/{connection_id}",
        headers=_headers(token, org_id),
        json={
            "webhookEvent": "jira:issue_updated",
            "timestamp": "evt-1",
            "issue": {"id": "10001", "key": "CPL-10001", "fields": {"status": {"name": "In Progress"}}},
            "comment": {"id": "9001", "body": "Inbound note", "author": {"accountId": "jira-user-1"}},
        },
    )
    assert inbound_response.status_code == 200, inbound_response.text
    assert inbound_response.json()["status"] == "processed"

    db_session.expire_all()
    issue_row = (
        db_session.query(Issue)
        .filter(Issue.organization_id == uuid.UUID(org_id), Issue.id == uuid.UUID(issue_id))
        .one()
    )
    assert issue_row.status == "investigating"

    comments = (
        db_session.query(IssueSyncComment)
        .filter(IssueSyncComment.organization_id == uuid.UUID(org_id), IssueSyncComment.issue_id == uuid.UUID(issue_id))
        .all()
    )
    directions = {row.direction for row in comments}
    assert {"inbound", "outbound"}.issubset(directions)

    events = (
        db_session.query(ExternalSyncEvent)
        .filter(ExternalSyncEvent.organization_id == uuid.UUID(org_id))
        .all()
    )
    assert len(events) >= 2
    assert {row.direction for row in events} == {"outbound", "inbound"}

    audit_actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org_id))
        .all()
    }
    assert "issue_sync.outbound_synced" in audit_actions
    assert "issue_sync.inbound_processed" in audit_actions


def test_i3_linear_inbound_only_rejects_outbound_and_ignores_unknown_link(client, db_session):
    token = _register(client, "i3-owner-b@example.com", "I3 Org B")
    org_id = _org_id(client, token)

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Linear Product",
            "provider": "linear",
            "entity_type": "issue",
            "direction_mode": "inbound_only",
            "credentials_json": {"api_key": "linear-key"},
            "field_mapping_json": {"linear_status_to_internal": {"In Progress": "investigating"}},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = connection_response.json()["id"]

    issue_id = str(uuid.uuid4())
    outbound_response = client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/sync/outbound",
        headers=_headers(token, org_id),
        json={"issue_id": issue_id, "include_status": True},
    )
    assert outbound_response.status_code == 422
    assert "does not allow outbound sync" in outbound_response.text

    inbound_response = client.post(
        f"/api/v1/issue-sync/webhooks/linear/{connection_id}",
        headers=_headers(token, org_id),
        json={
            "id": "evt-linear-1",
            "type": "Issue",
            "action": "update",
            "data": {"id": "lin-101", "identifier": "LIN-101", "state": {"name": "In Progress"}},
        },
    )
    assert inbound_response.status_code == 200, inbound_response.text
    assert inbound_response.json()["status"] == "ignored"

    events = (
        db_session.query(ExternalSyncEvent)
        .filter(ExternalSyncEvent.organization_id == uuid.UUID(org_id), ExternalSyncEvent.connection_id == uuid.UUID(connection_id))
        .all()
    )
    assert len(events) == 1
    assert events[0].status == "ignored"


def test_i3_outbound_comment_requires_body(client, db_session, monkeypatch):
    token = _register(client, "i3-owner-c@example.com", "I3 Org C")
    org_id = _org_id(client, token)
    user = _user(db_session, "i3-owner-c@example.com")
    issue_id = _create_issue(client, token, org_id, str(user.id))

    monkeypatch.setattr(IssueSyncService, "_send_outbound_linear", lambda self, **kwargs: {"provider": "linear"})

    connection_response = client.post(
        "/api/v1/issue-sync/connections",
        headers=_headers(token, org_id),
        json={
            "name": "Linear Ops",
            "provider": "linear",
            "entity_type": "issue",
            "direction_mode": "two_way",
            "credentials_json": {"api_key": "linear-key"},
        },
    )
    assert connection_response.status_code == 201, connection_response.text
    connection_id = connection_response.json()["id"]

    link_response = client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/links",
        headers=_headers(token, org_id),
        json={"entity_type": "issue", "internal_entity_id": issue_id, "external_entity_id": "lin-500"},
    )
    assert link_response.status_code == 201, link_response.text

    outbound_response = client.post(
        f"/api/v1/issue-sync/connections/{connection_id}/sync/outbound",
        headers=_headers(token, org_id),
        json={"issue_id": issue_id, "include_status": False, "include_comment": True},
    )
    assert outbound_response.status_code == 422
    assert "comment_body is required" in outbound_response.text
