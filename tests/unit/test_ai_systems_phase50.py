import uuid

from app.core.security import get_password_hash
from app.models.ai_system import AISystem
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


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


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Fraud Agent") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={
            "name": name,
            "system_type": "agent",
            "lifecycle_status": "proposed",
            "tags_json": ["core"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_ai_system_permissions_seeded(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p50-owner-seed")
    token = owner_bootstrap["access_token"]
    org_id = owner_bootstrap["organization_id"]

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "ai_systems:read" in keys
    assert "ai_systems:write" in keys
    assert "ai_systems:admin" in keys

    owner_permissions = client.get(
        "/api/v1/auth/permissions",
        headers=org_headers(token, org_id),
    )
    assert owner_permissions.status_code == 200
    permission_codes = owner_permissions.json()["permission_codes"]
    assert "ai_systems:read" in permission_codes
    assert "ai_systems:write" in permission_codes
    assert "ai_systems:admin" in permission_codes


def test_ai_system_create_and_owner_membership_validation(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p50-owner-create")
    other_bootstrap = bootstrap_org_user(client, email_prefix="p50-owner-other")
    owner_headers = owner_bootstrap["org_headers"]
    org_id = owner_bootstrap["organization_id"]

    same_org_owner = _create_active_user_with_role(db_session, org_id, "p50-owner-member@example.com", "admin")
    other_org_owner = _create_active_user_with_role(
        db_session,
        other_bootstrap["organization_id"],
        "p50-owner-other-member@example.com",
        "admin",
    )

    missing_name = client.post(
        "/api/v1/ai-systems",
        headers=owner_headers,
        json={"system_type": "agent"},
    )
    assert missing_name.status_code == 422

    valid = client.post(
        "/api/v1/ai-systems",
        headers=owner_headers,
        json={
            "name": "Support AI Assistant",
            "system_type": "ai_feature",
            "business_owner_user_id": str(same_org_owner.id),
            "technical_owner_user_id": str(same_org_owner.id),
            "provider_name": "Internal",
        },
    )
    assert valid.status_code == 201
    body = valid.json()
    assert body["name"] == "Support AI Assistant"
    assert body["lifecycle_status"] == "proposed"
    assert body["business_owner_user_id"] == str(same_org_owner.id)

    bad_owner = client.post(
        "/api/v1/ai-systems",
        headers=owner_headers,
        json={
            "name": "Bad Owner",
            "system_type": "agent",
            "business_owner_user_id": str(other_org_owner.id),
        },
    )
    assert bad_owner.status_code == 400
    assert "business_owner_user_id" in bad_owner.json()["detail"]


def test_ai_system_list_and_detail_are_tenant_scoped(client):
    owner1 = bootstrap_org_user(client, email_prefix="p50-owner-scope1")
    owner2 = bootstrap_org_user(client, email_prefix="p50-owner-scope2")

    row1 = _create_ai_system(client, owner1["org_headers"], name="Org1 AI")
    _create_ai_system(client, owner2["org_headers"], name="Org2 AI")

    list1 = client.get("/api/v1/ai-systems", headers=owner1["org_headers"])
    assert list1.status_code == 200
    assert [item["name"] for item in list1.json()] == ["Org1 AI"]

    detail_missing = client.get(
        f"/api/v1/ai-systems/{row1['id']}",
        headers=owner2["org_headers"],
    )
    assert detail_missing.status_code == 404


def test_ai_system_update_validates_owner_and_writes_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p50-owner-update")
    other_bootstrap = bootstrap_org_user(client, email_prefix="p50-owner-update-other")
    owner_headers = owner_bootstrap["org_headers"]
    org_id = owner_bootstrap["organization_id"]

    same_org_owner = _create_active_user_with_role(db_session, org_id, "p50-update-member@example.com", "admin")
    other_org_owner = _create_active_user_with_role(
        db_session,
        other_bootstrap["organization_id"],
        "p50-update-other-member@example.com",
        "admin",
    )

    created = _create_ai_system(client, owner_headers, name="Update Target")

    bad_update = client.patch(
        f"/api/v1/ai-systems/{created['id']}",
        headers=owner_headers,
        json={"technical_owner_user_id": str(other_org_owner.id)},
    )
    assert bad_update.status_code == 400
    assert "technical_owner_user_id" in bad_update.json()["detail"]

    updated = client.patch(
        f"/api/v1/ai-systems/{created['id']}",
        headers=owner_headers,
        json={
            "lifecycle_status": "production",
            "technical_owner_user_id": str(same_org_owner.id),
            "notes": "Validated for production",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["lifecycle_status"] == "production"
    assert updated.json()["technical_owner_user_id"] == str(same_org_owner.id)

    logs = client.get("/api/v1/audit-logs", headers=owner_headers)
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "ai_system.updated" in actions


def test_ai_system_archive_list_summary_and_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p50-owner-archive")
    org_id = owner_bootstrap["organization_id"]
    owner_token = owner_bootstrap["access_token"]
    owner_headers = owner_bootstrap["org_headers"]

    readonly_user = _create_active_user_with_role(db_session, org_id, "p50-readonly@example.com", "readonly")
    readonly_token = login_user(client, readonly_user.email)
    readonly_headers = org_headers(readonly_token, org_id)

    active_system = _create_ai_system(client, owner_headers, name="Active AI")
    archive_system = _create_ai_system(client, owner_headers, name="Archive AI")

    readonly_archive = client.post(
        f"/api/v1/ai-systems/{archive_system['id']}/archive",
        headers=readonly_headers,
        json={"reason": "No permission"},
    )
    assert readonly_archive.status_code == 403

    archived = client.post(
        f"/api/v1/ai-systems/{archive_system['id']}/archive",
        headers=owner_headers,
        json={"reason": "Retired service"},
    )
    assert archived.status_code == 200
    assert archived.json()["lifecycle_status"] == "archived"
    assert archived.json()["archived_at"] is not None

    archived_id = uuid.UUID(archive_system["id"])
    persisted = db_session.query(AISystem).filter(AISystem.id == archived_id, AISystem.organization_id == uuid.UUID(org_id)).one_or_none()
    assert persisted is not None
    assert persisted.lifecycle_status == "archived"

    list_default = client.get("/api/v1/ai-systems", headers=owner_headers)
    assert list_default.status_code == 200
    names_default = {item["name"] for item in list_default.json()}
    assert "Active AI" in names_default
    assert "Archive AI" not in names_default

    list_including_archived = client.get("/api/v1/ai-systems?include_archived=true", headers=owner_headers)
    assert list_including_archived.status_code == 200
    names_all = {item["name"] for item in list_including_archived.json()}
    assert "Active AI" in names_all
    assert "Archive AI" in names_all

    restricted_update = client.patch(
        f"/api/v1/ai-systems/{archive_system['id']}",
        headers=owner_headers,
        json={"name": "Should Fail"},
    )
    assert restricted_update.status_code == 400

    allowed_update = client.patch(
        f"/api/v1/ai-systems/{archive_system['id']}",
        headers=owner_headers,
        json={"notes": "archived note", "tags_json": ["retired"]},
    )
    assert allowed_update.status_code == 200

    summary = client.get("/api/v1/ai-systems/summary", headers=owner_headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_systems"] == 2
    assert body["active_systems"] == 1
    assert body["archived_systems"] == 1
    assert body["by_lifecycle_status"]["archived"] == 1
    assert body["by_system_type"]["agent"] == 2
    assert body["missing_owner_count"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=org_headers(owner_token, org_id))
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "ai_system.created" in actions
    assert "ai_system.archived" in actions
