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


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _create_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
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


def test_framework_catalog_and_detail_counts(client):
    owner_token = _register(client, "p20-owner1@example.com", "Pass1234!@", "P20 Org1")

    catalog = client.get("/api/v1/frameworks", headers=_headers(owner_token))
    assert catalog.status_code == 200
    items = catalog.json()
    assert len(items) >= 8
    codes = {item["code"] for item in items}
    assert {"EU_AI_ACT", "GDPR", "SOC2"}.issubset(codes)
    assert all(item["coverage_level"] in {"metadata_only", "starter", "partial", "mapped", "evidence_backed"} for item in items)

    framework_id = items[0]["id"]
    detail = client.get(f"/api/v1/frameworks/{framework_id}", headers=_headers(owner_token))
    assert detail.status_code == 200
    assert "obligation_count" in detail.json()
    assert "active_obligation_count" in detail.json()


def test_framework_activation_permissions_and_idempotency(client, db_session):
    owner_token = _register(client, "p20-owner2@example.com", "Pass1234!@", "P20 Org2")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]

    frameworks = client.get("/api/v1/frameworks", headers=_headers(owner_token)).json()
    framework_id = frameworks[0]["id"]

    admin_user = _create_user_with_role(db_session, org_id, "p20-admin@example.com", "admin")
    cm_user = _create_user_with_role(db_session, org_id, "p20-cm@example.com", "compliance_manager")
    readonly_user = _create_user_with_role(db_session, org_id, "p20-ro@example.com", "readonly")
    auditor_user = _create_user_with_role(db_session, org_id, "p20-au@example.com", "auditor")

    admin_token = _login(client, admin_user.email, "Pass1234!@")
    cm_token = _login(client, cm_user.email, "Pass1234!@")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")
    auditor_token = _login(client, auditor_user.email, "Pass1234!@")

    owner_activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(owner_token, org_id),
        json={"notes": "enable"},
    )
    assert owner_activate.status_code == 200
    activation_id = owner_activate.json()["id"]

    idempotent = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(owner_token, org_id),
        json={"notes": "enable again"},
    )
    assert idempotent.status_code == 200
    assert idempotent.json()["id"] == activation_id

    admin_activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(admin_token, org_id),
        json={"notes": "admin"},
    )
    assert admin_activate.status_code == 200

    cm_activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(cm_token, org_id),
        json={"notes": "cm"},
    )
    assert cm_activate.status_code == 200

    ro_activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(readonly_token, org_id),
        json={"notes": "ro"},
    )
    assert ro_activate.status_code == 403

    auditor_activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(auditor_token, org_id),
        json={"notes": "aud"},
    )
    assert auditor_activate.status_code == 403


def test_framework_activation_is_tenant_scoped_and_deactivation_audited(client):
    owner1 = _register(client, "p20-owner3@example.com", "Pass1234!@", "P20 Org3")
    owner2 = _register(client, "p20-owner4@example.com", "Pass1234!@", "P20 Org4")

    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]
    org2 = client.get("/api/v1/organizations/me", headers=_headers(owner2)).json()[0]["id"]

    framework_id = client.get("/api/v1/frameworks", headers=_headers(owner1)).json()[0]["id"]

    activate = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(owner1, org1),
        json={"notes": "activate org1"},
    )
    assert activate.status_code == 200

    active_org1 = client.get("/api/v1/frameworks/active", headers=_headers(owner1, org1))
    active_org2 = client.get("/api/v1/frameworks/active", headers=_headers(owner2, org2))
    assert active_org1.status_code == 200
    assert active_org2.status_code == 200
    assert len(active_org1.json()) >= 1
    assert active_org2.json() == []

    deactivate = client.post(
        f"/api/v1/frameworks/{framework_id}/deactivate",
        headers=_headers(owner1, org1),
        json={"notes": "off"},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "inactive"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1))
    actions = [item["action"] for item in logs.json()]
    assert "framework.activated" in actions
    assert "framework.deactivated" in actions


def test_obligation_list_detail_and_state_update_rules(client):
    owner = _register(client, "p20-owner5@example.com", "Pass1234!@", "P20 Org5")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner)).json()[0]["id"]

    frameworks = client.get("/api/v1/frameworks", headers=_headers(owner)).json()
    framework_id = frameworks[0]["id"]

    obligations = client.get(f"/api/v1/frameworks/{framework_id}/obligations", headers=_headers(owner))
    assert obligations.status_code == 200

    if obligations.json():
        obligation_id = obligations.json()[0]["id"]
        detail = client.get(f"/api/v1/obligations/{obligation_id}", headers=_headers(owner, org_id))
        assert detail.status_code == 200

    # find framework with obligations, then activate and update state
    framework_with_obligations = None
    obligation_for_update = None
    for fw in frameworks:
        resp = client.get(f"/api/v1/frameworks/{fw['id']}/obligations", headers=_headers(owner))
        if resp.status_code == 200 and resp.json():
            framework_with_obligations = fw["id"]
            obligation_for_update = resp.json()[0]["id"]
            break

    assert framework_with_obligations is not None
    assert obligation_for_update is not None

    not_active_update = client.patch(
        f"/api/v1/obligations/{obligation_for_update}/state",
        headers=_headers(owner, org_id),
        json={"applicability_status": "applicable", "implementation_status": "in_progress"},
    )
    assert not_active_update.status_code == 400

    activate = client.post(
        f"/api/v1/frameworks/{framework_with_obligations}/activate",
        headers=_headers(owner, org_id),
        json={"notes": "activate for state"},
    )
    assert activate.status_code == 200

    bad_na = client.patch(
        f"/api/v1/obligations/{obligation_for_update}/state",
        headers=_headers(owner, org_id),
        json={"applicability_status": "not_applicable", "implementation_status": "blocked"},
    )
    assert bad_na.status_code == 400

    good_update = client.patch(
        f"/api/v1/obligations/{obligation_for_update}/state",
        headers=_headers(owner, org_id),
        json={
            "applicability_status": "applicable",
            "implementation_status": "in_progress",
            "justification": "Initial assessment",
        },
    )
    assert good_update.status_code == 200
    assert good_update.json()["organization_state"]["implementation_status"] == "in_progress"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id))
    assert logs.status_code == 200
    assert "obligation.state_updated" in [item["action"] for item in logs.json()]
