import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/vendors"


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


def _create_vendor(client, headers: dict[str, str], *, owner_user_id: str, name: str = "Acme Vendor") -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": "not_assessed",
            "status": "active",
            "data_access": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_phase93_permissions_seeded(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p93-perms")

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "vendors:read" in keys
    assert "vendors:write" in keys
    assert "vendors:admin" in keys

    perms = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "vendors:read" in codes
    assert "vendors:write" in codes
    assert "vendors:admin" in codes


def test_phase93_vendor_crud_and_owner_validation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p93-crud")
    other_org = bootstrap_org_user(client, email_prefix="p93-crud-other")

    same_org_owner = _create_active_user_with_role(db_session, org["organization_id"], "p93-owner@example.com", "admin")
    other_org_owner = _create_active_user_with_role(
        db_session,
        other_org["organization_id"],
        "p93-other-owner@example.com",
        "admin",
    )

    missing_name = client.post(
        BASE,
        headers=org["org_headers"],
        json={"vendor_type": "software", "owner_user_id": str(same_org_owner.id)},
    )
    assert missing_name.status_code == 422

    bad_owner = client.post(
        BASE,
        headers=org["org_headers"],
        json={"name": "Bad Owner", "vendor_type": "software", "owner_user_id": str(other_org_owner.id)},
    )
    assert bad_owner.status_code == 400
    assert "owner_user_id" in bad_owner.json()["detail"]

    created = _create_vendor(client, org["org_headers"], owner_user_id=str(same_org_owner.id), name="Vendor One")
    assert created["name"] == "Vendor One"
    assert created["status"] == "active"

    detail = client.get(f"{BASE}/{created['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]

    updated = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"risk_tier": "high", "status": "under_review", "notes": "risk assessment initiated"},
    )
    assert updated.status_code == 200
    assert updated.json()["risk_tier"] == "high"
    assert updated.json()["status"] == "under_review"


def test_phase93_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p93-scope1")
    org2 = bootstrap_org_user(client, email_prefix="p93-scope2")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "p93-scope-owner1@example.com", "admin")
    _create_active_user_with_role(db_session, org2["organization_id"], "p93-scope-owner2@example.com", "admin")

    v1 = _create_vendor(client, org1["org_headers"], owner_user_id=str(owner1.id), name="Org1 Vendor")

    list1 = client.get(BASE, headers=org1["org_headers"])
    list2 = client.get(BASE, headers=org2["org_headers"])
    assert list1.status_code == 200
    assert list2.status_code == 200
    assert [row["name"] for row in list1.json()] == ["Org1 Vendor"]
    assert list2.json() == []

    cross_detail = client.get(f"{BASE}/{v1['id']}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404


def test_phase93_archive_behavior_and_include_archived(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p93-archive")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p93-archive-owner@example.com", "admin")

    active = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Active Vendor")
    to_archive = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Archive Vendor")

    archived = client.post(
        f"{BASE}/{to_archive['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "contract terminated"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None

    blocked_update = client.patch(
        f"{BASE}/{to_archive['id']}",
        headers=org["org_headers"],
        json={"name": "Should Fail"},
    )
    assert blocked_update.status_code == 400

    allowed_update = client.patch(
        f"{BASE}/{to_archive['id']}",
        headers=org["org_headers"],
        json={"notes": "archived note", "tags_json": ["legacy"]},
    )
    assert allowed_update.status_code == 200

    list_default = client.get(BASE, headers=org["org_headers"])
    assert list_default.status_code == 200
    names_default = {row["name"] for row in list_default.json()}
    assert names_default == {"Active Vendor"}

    list_all = client.get(f"{BASE}?include_archived=true", headers=org["org_headers"])
    assert list_all.status_code == 200
    names_all = {row["name"] for row in list_all.json()}
    assert names_all == {"Active Vendor", "Archive Vendor"}

    _ = active


def test_phase93_summary_and_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p93-summary")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p93-summary-owner@example.com", "admin")

    v1 = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="V1")
    v2 = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="V2")

    patch_v1 = client.patch(
        f"{BASE}/{v1['id']}",
        headers=org["org_headers"],
        json={"risk_tier": "critical", "vendor_type": "infrastructure", "status": "under_review"},
    )
    assert patch_v1.status_code == 200

    patch_v2 = client.patch(
        f"{BASE}/{v2['id']}",
        headers=org["org_headers"],
        json={"risk_tier": "low", "vendor_type": "professional_services"},
    )
    assert patch_v2.status_code == 200

    archived = client.post(
        f"{BASE}/{v2['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "end of engagement"},
    )
    assert archived.status_code == 200

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_vendors"] == 2
    assert body["active_vendors"] == 1
    assert body["archived_vendors"] == 1
    assert body["by_status"]["under_review"] == 1
    assert body["by_status"]["archived"] == 1
    assert body["by_risk_tier"]["critical"] == 1
    assert body["by_risk_tier"]["low"] == 1
    assert body["by_vendor_type"]["infrastructure"] == 1
    assert body["by_vendor_type"]["professional_services"] == 1

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "vendor.created" in actions
    assert "vendor.updated" in actions
    assert "vendor.archived" in actions
