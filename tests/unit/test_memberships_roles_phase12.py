import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
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


def _create_active_user_with_role(db_session, organization_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
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


def test_owner_can_list_members_and_roles_are_org_scoped(client):
    owner1 = _register(client, "phase12-owner1@example.com", "Pass1234!@", "Phase12 Org1")
    owner2 = _register(client, "phase12-owner2@example.com", "Pass1234!@", "Phase12 Org2")

    org1_id = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]
    org2_id = client.get("/api/v1/organizations/me", headers=_headers(owner2)).json()[0]["id"]

    members = client.get("/api/v1/memberships", headers=_headers(owner1, org1_id))
    assert members.status_code == 200
    assert all(item["organization_id"] == org1_id for item in members.json())

    roles_1 = client.get("/api/v1/roles", headers=_headers(owner1, org1_id))
    roles_2 = client.get("/api/v1/roles", headers=_headers(owner2, org2_id))
    assert roles_1.status_code == 200
    assert roles_2.status_code == 200
    role_ids_1 = {item["id"] for item in roles_1.json()}
    role_ids_2 = {item["id"] for item in roles_2.json()}
    assert role_ids_1
    assert role_ids_2
    assert role_ids_1.isdisjoint(role_ids_2)


def test_readonly_cannot_invite_or_update_role(client, db_session):
    owner_token = _register(client, "phase12-owner3@example.com", "Pass1234!@", "Phase12 Org3")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]

    readonly_user = _create_active_user_with_role(db_session, org_id, "phase12-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")

    invite_resp = client.post(
        "/api/v1/memberships",
        headers=_headers(readonly_token, org_id),
        json={"email": "phase12-invite1@example.com", "role_name": "reviewer"},
    )
    assert invite_resp.status_code == 403

    owner_memberships = client.get("/api/v1/memberships", headers=_headers(owner_token, org_id)).json()
    target_membership_id = next(item["id"] for item in owner_memberships if item["user"]["email"] == readonly_user.email)
    update_resp = client.patch(
        f"/api/v1/memberships/{target_membership_id}/role",
        headers=_headers(readonly_token, org_id),
        json={"role_name": "reviewer"},
    )
    assert update_resp.status_code == 403


def test_owner_admin_can_create_membership_and_membership_is_tenant_scoped(client, db_session):
    owner_token = _register(client, "phase12-owner4@example.com", "Pass1234!@", "Phase12 Org4")
    other_owner_token = _register(client, "phase12-owner5@example.com", "Pass1234!@", "Phase12 Org5")

    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    other_org_id = client.get("/api/v1/organizations/me", headers=_headers(other_owner_token)).json()[0]["id"]

    admin_user = _create_active_user_with_role(db_session, org_id, "phase12-admin@example.com", "admin")
    admin_token = _login(client, admin_user.email, "Pass1234!@")

    created = client.post(
        "/api/v1/memberships",
        headers=_headers(admin_token, org_id),
        json={"email": "phase12-newmember@example.com", "full_name": "New Member", "role_name": "reviewer"},
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["organization_id"] == org_id
    created_membership_id = created_body["id"]

    own_org_get = client.get(
        f"/api/v1/memberships/{created_membership_id}",
        headers=_headers(owner_token, org_id),
    )
    assert own_org_get.status_code == 200

    cross_tenant_get = client.get(
        f"/api/v1/memberships/{created_membership_id}",
        headers=_headers(other_owner_token, other_org_id),
    )
    assert cross_tenant_get.status_code == 404


def test_owner_can_update_role_and_deactivate_with_audit_and_last_owner_protection(client):
    owner_token = _register(client, "phase12-owner6@example.com", "Pass1234!@", "Phase12 Org6")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]

    create_member = client.post(
        "/api/v1/memberships",
        headers=_headers(owner_token, org_id),
        json={"email": "phase12-member2@example.com", "role_name": "reviewer"},
    )
    assert create_member.status_code == 201
    membership_id = create_member.json()["id"]

    role_update = client.patch(
        f"/api/v1/memberships/{membership_id}/role",
        headers=_headers(owner_token, org_id),
        json={"role_name": "auditor"},
    )
    assert role_update.status_code == 200
    assert role_update.json()["role_name"] == "auditor"

    deactivate = client.patch(
        f"/api/v1/memberships/{membership_id}/deactivate",
        headers=_headers(owner_token, org_id),
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "inactive"

    memberships = client.get("/api/v1/memberships", headers=_headers(owner_token, org_id)).json()
    owner_membership_id = next(item["id"] for item in memberships if item["role_name"] == "owner" and item["status"] == "active")

    cannot_downgrade_last_owner = client.patch(
        f"/api/v1/memberships/{owner_membership_id}/role",
        headers=_headers(owner_token, org_id),
        json={"role_name": "admin"},
    )
    assert cannot_downgrade_last_owner.status_code == 400

    cannot_deactivate_last_owner = client.patch(
        f"/api/v1/memberships/{owner_membership_id}/deactivate",
        headers=_headers(owner_token, org_id),
    )
    assert cannot_deactivate_last_owner.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner_token, org_id))
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "membership.role_updated" in actions
    assert "membership.deactivated" in actions


def test_auth_permissions_returns_current_org_permissions(client):
    owner_token = _register(client, "phase12-owner7@example.com", "Pass1234!@", "Phase12 Org7")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]

    permissions = client.get("/api/v1/auth/permissions", headers=_headers(owner_token, org_id))
    assert permissions.status_code == 200
    codes = permissions.json()["permission_codes"]
    assert "users:read" in codes
    assert "users:invite" in codes
    assert "users:update_role" in codes
