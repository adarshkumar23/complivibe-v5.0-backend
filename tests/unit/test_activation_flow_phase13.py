from datetime import UTC, timedelta, datetime
import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.membership_activation_token import MembershipActivationToken
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


def _headers(token: str, organization_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id:
        headers["X-Organization-ID"] = organization_id
    return headers


def _create_active_user_with_role(db_session, organization_id: str, email: str, role_name: str) -> User:
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

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(organization_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(organization_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _invite_member(client, token: str, org_id: str, email: str) -> str:
    response = client.post(
        "/api/v1/memberships",
        headers=_headers(token, org_id),
        json={"email": email, "role_name": "reviewer"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_owner_can_generate_activation_token_and_hash_stored(client, db_session):
    owner_token = _register(client, "p13-owner1@example.com", "Pass1234!@", "P13 Org1")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    membership_id = _invite_member(client, owner_token, org_id, "p13-invited1@example.com")

    token_resp = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    assert token_resp.status_code == 200
    body = token_resp.json()
    raw_token = body["activation_token"]
    assert body["warning"] == "Token is shown only once. Store it securely."
    assert raw_token

    token_row = db_session.query(MembershipActivationToken).filter_by(membership_id=uuid.UUID(membership_id)).one()
    assert token_row.token_hash
    assert token_row.token_hash != raw_token


def test_readonly_cannot_generate_activation_token(client, db_session):
    owner_token = _register(client, "p13-owner2@example.com", "Pass1234!@", "P13 Org2")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    readonly_user = _create_active_user_with_role(db_session, org_id, "p13-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")

    membership_id = _invite_member(client, owner_token, org_id, "p13-invited2@example.com")
    response = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(readonly_token, org_id),
    )
    assert response.status_code == 403


def test_activate_invite_success_login_and_used_token_protection(client, db_session):
    owner_token = _register(client, "p13-owner3@example.com", "Pass1234!@", "P13 Org3")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    invited_email = "p13-invited3@example.com"
    membership_id = _invite_member(client, owner_token, org_id, invited_email)

    token_resp = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    raw_token = token_resp.json()["activation_token"]

    activate_resp = client.post(
        "/api/v1/auth/activate-invite",
        json={
            "activation_token": raw_token,
            "password": "StrongPass123!",
            "full_name": "Invited User",
        },
    )
    assert activate_resp.status_code == 200

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": invited_email, "password": "StrongPass123!"},
    )
    assert login_resp.status_code == 200

    token_row = db_session.query(MembershipActivationToken).filter_by(membership_id=uuid.UUID(membership_id)).one()
    assert token_row.status == "used"
    assert token_row.used_at is not None

    reuse = client.post(
        "/api/v1/auth/activate-invite",
        json={"activation_token": raw_token, "password": "StrongPass123!"},
    )
    assert reuse.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner_token, org_id))
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "membership.invitation_accepted" in actions


def test_expired_and_revoked_tokens_cannot_be_used(client, db_session):
    owner_token = _register(client, "p13-owner4@example.com", "Pass1234!@", "P13 Org4")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]

    membership_id = _invite_member(client, owner_token, org_id, "p13-invited4@example.com")
    created = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    raw_token = created.json()["activation_token"]

    token_row = db_session.query(MembershipActivationToken).filter_by(membership_id=uuid.UUID(membership_id)).one()
    token_row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    token_row.status = "active"
    db_session.commit()

    expired_use = client.post(
        "/api/v1/auth/activate-invite",
        json={"activation_token": raw_token, "password": "StrongPass123!"},
    )
    assert expired_use.status_code == 400

    membership_id2 = _invite_member(client, owner_token, org_id, "p13-invited5@example.com")
    created2 = client.post(
        f"/api/v1/memberships/{membership_id2}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    raw_token2 = created2.json()["activation_token"]

    revoke = client.post(
        f"/api/v1/memberships/{membership_id2}/activation-token/revoke",
        headers=_headers(owner_token, org_id),
    )
    assert revoke.status_code == 200

    revoked_use = client.post(
        "/api/v1/auth/activate-invite",
        json={"activation_token": raw_token2, "password": "StrongPass123!"},
    )
    assert revoked_use.status_code == 400


def test_new_token_revokes_previous_and_status_endpoint_hides_secret(client, db_session):
    owner_token = _register(client, "p13-owner5@example.com", "Pass1234!@", "P13 Org5")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    membership_id = _invite_member(client, owner_token, org_id, "p13-invited6@example.com")

    first = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    first_token = first.json()["activation_token"]

    second = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    second_token = second.json()["activation_token"]
    assert first_token != second_token

    old_use = client.post(
        "/api/v1/auth/activate-invite",
        json={"activation_token": first_token, "password": "StrongPass123!"},
    )
    assert old_use.status_code == 400

    status_resp = client.get(
        f"/api/v1/memberships/{membership_id}/activation-token/status",
        headers=_headers(owner_token, org_id),
    )
    assert status_resp.status_code == 200
    status_json = status_resp.json()
    assert "activation_token" not in status_json
    assert "token_hash" not in status_json
    assert status_json["has_active_token"] is True

    token_rows = db_session.query(MembershipActivationToken).filter_by(membership_id=uuid.UUID(membership_id)).all()
    statuses = sorted([row.status for row in token_rows])
    assert "revoked" in statuses
    assert "active" in statuses


def test_activation_and_revoke_write_audit_logs_and_cross_tenant_forbidden(client):
    owner_token = _register(client, "p13-owner6@example.com", "Pass1234!@", "P13 Org6")
    other_owner_token = _register(client, "p13-owner7@example.com", "Pass1234!@", "P13 Org7")

    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    other_org_id = client.get("/api/v1/organizations/me", headers=_headers(other_owner_token)).json()[0]["id"]

    membership_id = _invite_member(client, owner_token, org_id, "p13-invited7@example.com")

    cross = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(other_owner_token, other_org_id),
    )
    assert cross.status_code == 403

    create_token = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token",
        headers=_headers(owner_token, org_id),
    )
    assert create_token.status_code == 200

    revoke = client.post(
        f"/api/v1/memberships/{membership_id}/activation-token/revoke",
        headers=_headers(owner_token, org_id),
    )
    assert revoke.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner_token, org_id))
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "membership.activation_token_created" in actions
    assert "membership.activation_token_revoked" in actions
