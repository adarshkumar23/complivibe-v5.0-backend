import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "organization_name": org_name,
            "full_name": "Test User",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth_headers(token: str, organization_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id is not None:
        headers["X-Organization-ID"] = organization_id
    return headers


def test_register_login_and_me(client):
    token = _register(client, "owner1@example.com", "strongpass123", "Org One")

    me_response = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "owner1@example.com"

    login_token = _login(client, "owner1@example.com", "strongpass123")
    assert isinstance(login_token, str)
    assert login_token


def test_missing_organization_header_fails(client):
    token = _register(client, "owner2@example.com", "strongpass123", "Org Two")
    orgs_response = client.get("/api/v1/organizations/me", headers=_auth_headers(token))
    organization_id = orgs_response.json()[0]["id"]

    response = client.get(f"/api/v1/organizations/{organization_id}", headers=_auth_headers(token))
    assert response.status_code == 400
    assert "X-Organization-ID" in response.json()["detail"]


def test_user_cannot_access_other_organization(client):
    token_org1 = _register(client, "owner3@example.com", "strongpass123", "Org Three")
    token_org2 = _register(client, "owner4@example.com", "strongpass123", "Org Four")

    org2_id = client.get("/api/v1/organizations/me", headers=_auth_headers(token_org2)).json()[0]["id"]
    response = client.get(
        f"/api/v1/organizations/{org2_id}",
        headers=_auth_headers(token_org1, org2_id),
    )
    assert response.status_code == 403


def test_readonly_cannot_update_org_owner_can_and_audit_logged(client, db_session):
    owner_token = _register(client, "owner5@example.com", "strongpass123", "Org Five")
    org_id = client.get("/api/v1/organizations/me", headers=_auth_headers(owner_token)).json()[0]["id"]

    readonly_user = User(
        email="readonly@example.com",
        full_name="Readonly",
        hashed_password=get_password_hash("readonlypass123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(readonly_user)
    db_session.flush()

    readonly_role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == "readonly").one()
    readonly_membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=readonly_user.id,
        role_id=readonly_role.id,
    )
    db_session.add(readonly_membership)
    db_session.commit()

    readonly_token = _login(client, "readonly@example.com", "readonlypass123")
    readonly_update = client.patch(
        f"/api/v1/organizations/{org_id}",
        headers=_auth_headers(readonly_token, org_id),
        json={"name": "Org Five Updated By Readonly"},
    )
    assert readonly_update.status_code == 403

    owner_update = client.patch(
        f"/api/v1/organizations/{org_id}",
        headers=_auth_headers(owner_token, org_id),
        json={"name": "Org Five Updated"},
    )
    assert owner_update.status_code == 200
    assert owner_update.json()["organization"]["name"] == "Org Five Updated"

    logs_response = client.get("/api/v1/audit-logs", headers=_auth_headers(owner_token, org_id))
    assert logs_response.status_code == 200
    actions = [item["action"] for item in logs_response.json()]
    assert "organization.updated" in actions


def test_audit_logs_are_tenant_scoped(client):
    token1 = _register(client, "owner6@example.com", "strongpass123", "Org Six")
    token2 = _register(client, "owner7@example.com", "strongpass123", "Org Seven")

    org1_id = client.get("/api/v1/organizations/me", headers=_auth_headers(token1)).json()[0]["id"]
    org2_id = client.get("/api/v1/organizations/me", headers=_auth_headers(token2)).json()[0]["id"]

    update_response = client.patch(
        f"/api/v1/organizations/{org1_id}",
        headers=_auth_headers(token1, org1_id),
        json={"name": "Org Six Updated"},
    )
    assert update_response.status_code == 200

    forbidden = client.get("/api/v1/audit-logs", headers=_auth_headers(token1, org2_id))
    assert forbidden.status_code == 403

    own_logs = client.get("/api/v1/audit-logs", headers=_auth_headers(token1, org1_id))
    assert own_logs.status_code == 200
    assert all(item["organization_id"] == org1_id for item in own_logs.json())
