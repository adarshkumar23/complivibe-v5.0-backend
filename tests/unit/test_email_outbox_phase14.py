import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def test_email_permissions_seeded(client, db_session):
    _register(client, "p14-owner1@example.com", "Pass1234!@", "P14 Org1")
    keys = {p.key for p in db_session.query(Permission).all()}
    assert {"email:read", "email:write", "email:send", "email:admin"}.issubset(keys)


def test_template_create_permissions_and_tenant_listing(client, db_session):
    owner1 = _register(client, "p14-owner2@example.com", "Pass1234!@", "P14 Org2")
    owner2 = _register(client, "p14-owner3@example.com", "Pass1234!@", "P14 Org3")
    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]
    org2 = client.get("/api/v1/organizations/me", headers=_headers(owner2)).json()[0]["id"]

    readonly_user = _create_active_user_with_role(db_session, org1, "p14-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")

    list1 = client.get("/api/v1/email/templates", headers=_headers(owner1, org1))
    list2 = client.get("/api/v1/email/templates", headers=_headers(owner2, org2))
    assert list1.status_code == 200
    assert list2.status_code == 200
    global_template_keys = {"invited_user_activation", "task_assigned", "evidence_requested", "control_owner_reminder"}
    assert global_template_keys.issubset({tpl["template_key"] for tpl in list1.json()})

    ro_create = client.post(
        "/api/v1/email/templates",
        headers=_headers(readonly_token, org1),
        json={
            "template_key": "custom_notice",
            "name": "Custom Notice",
            "subject_template": "Hello {{ user_name }}",
            "body_text_template": "Body {{ user_name }}",
            "allowed_variables_json": ["user_name"],
        },
    )
    assert ro_create.status_code == 403

    owner_create = client.post(
        "/api/v1/email/templates",
        headers=_headers(owner1, org1),
        json={
            "template_key": "custom_notice",
            "name": "Custom Notice",
            "subject_template": "Hello {{ user_name }}",
            "body_text_template": "Body {{ user_name }}",
            "allowed_variables_json": ["user_name"],
        },
    )
    assert owner_create.status_code == 201

    list_after = client.get("/api/v1/email/templates", headers=_headers(owner1, org1)).json()
    assert any(t["template_key"] == "custom_notice" and t["organization_id"] == org1 for t in list_after)

    other_org_list = client.get("/api/v1/email/templates", headers=_headers(owner2, org2)).json()
    assert not any(t["template_key"] == "custom_notice" and t["organization_id"] == org1 for t in other_org_list)


def test_template_preview_validation_and_outbox_flow(client):
    owner = _register(client, "p14-owner4@example.com", "Pass1234!@", "P14 Org4")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner)).json()[0]["id"]

    templates = client.get("/api/v1/email/templates", headers=_headers(owner, org_id)).json()
    activation_tpl = next(t for t in templates if t["template_key"] == "invited_user_activation")

    bad_preview = client.post(
        f"/api/v1/email/templates/{activation_tpl['id']}/preview",
        headers=_headers(owner, org_id),
        json={"variables_json": {"user_name": "Alice", "activation_link": "https://x", "unknown": "x"}},
    )
    assert bad_preview.status_code == 400

    ok_preview = client.post(
        f"/api/v1/email/templates/{activation_tpl['id']}/preview",
        headers=_headers(owner, org_id),
        json={"variables_json": {"user_name": "Alice", "activation_link": "https://x"}},
    )
    assert ok_preview.status_code == 200
    assert "Alice" in ok_preview.json()["subject"] or "Alice" in ok_preview.json()["body_text"]

    queued = client.post(
        "/api/v1/email/outbox",
        headers=_headers(owner, org_id),
        json={
            "template_id": activation_tpl["id"],
            "recipient_email": "invitee@example.com",
            "event_type": "invitation.created",
            "variables_json": {"user_name": "Invitee", "activation_link": "https://activate"},
            "priority": "high",
        },
    )
    assert queued.status_code == 201
    email_id = queued.json()["id"]
    assert queued.json()["status"] == "pending"
    assert queued.json()["sent_at"] is None

    outbox_list = client.get("/api/v1/email/outbox", headers=_headers(owner, org_id))
    assert outbox_list.status_code == 200
    assert any(item["id"] == email_id for item in outbox_list.json())

    detail = client.get(f"/api/v1/email/outbox/{email_id}", headers=_headers(owner, org_id))
    assert detail.status_code == 200
    assert len(detail.json()["delivery_events"]) >= 1

    cancelled = client.post(f"/api/v1/email/outbox/{email_id}/cancel", headers=_headers(owner, org_id))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    sent = client.post(f"/api/v1/email/outbox/{email_id}/mark-sent", headers=_headers(owner, org_id))
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    failed = client.post(
        f"/api/v1/email/outbox/{email_id}/mark-failed",
        headers=_headers(owner, org_id),
        json={"error_message": "Manual failure for test"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id)).json()
    actions = [item["action"] for item in logs]
    assert "email.queued" in actions
    assert "email.cancelled" in actions
    assert "email.marked_sent" in actions
    assert "email.marked_failed" in actions


def test_outbox_tenant_scope(client):
    owner1 = _register(client, "p14-owner5@example.com", "Pass1234!@", "P14 Org5")
    owner2 = _register(client, "p14-owner6@example.com", "Pass1234!@", "P14 Org6")
    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]
    org2 = client.get("/api/v1/organizations/me", headers=_headers(owner2)).json()[0]["id"]

    templates = client.get("/api/v1/email/templates", headers=_headers(owner1, org1)).json()
    tpl = next(t for t in templates if t["template_key"] == "task_assigned")

    queued = client.post(
        "/api/v1/email/outbox",
        headers=_headers(owner1, org1),
        json={
            "template_id": tpl["id"],
            "recipient_email": "x@example.com",
            "event_type": "task.assigned",
            "variables_json": {"user_name": "Bob", "task_title": "Do thing"},
        },
    )
    assert queued.status_code == 201
    email_id = queued.json()["id"]

    cross_detail = client.get(f"/api/v1/email/outbox/{email_id}", headers=_headers(owner2, org2))
    assert cross_detail.status_code == 404
