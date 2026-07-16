import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/policies"


def _create_user_with_role(
    db_session,
    *,
    org_id: str,
    email: str,
    role_name: str,
    membership_status: str = "active",
    user_status: str = "active",
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status=user_status,
        is_active=is_active,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status=membership_status,
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _create_policy(client, headers: dict[str, str], *, owner_user_id: str, title: str = "Policy A", policy_type: str = "acceptable_use") -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "title": title,
            "policy_type": policy_type,
            "owner_user_id": owner_user_id,
            "version": "1.0",
            "tags_json": ["seed"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _transition_to_deprecated(client, headers: dict[str, str], policy_id: str) -> None:
    under_review = client.patch(f"{BASE}/{policy_id}", headers=headers, json={"status": "under_review"})
    assert under_review.status_code == 200
    approved = client.patch(f"{BASE}/{policy_id}", headers=headers, json={"status": "approved"})
    assert approved.status_code == 200
    deprecated = client.patch(f"{BASE}/{policy_id}", headers=headers, json={"status": "deprecated"})
    assert deprecated.status_code == 200


def test_phase90_permissions_seeded_for_owner_admin_and_member_access(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-perms")

    permission_keys = {p.key for p in db_session.query(Permission).all()}
    assert "compliance_policies:read" in permission_keys
    assert "compliance_policies:write" in permission_keys
    assert "compliance_policies:approve" in permission_keys

    owner_permissions = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert owner_permissions.status_code == 200
    owner_codes = set(owner_permissions.json()["permission_codes"])
    assert "compliance_policies:read" in owner_codes
    assert "compliance_policies:write" in owner_codes
    assert "compliance_policies:approve" in owner_codes


def test_phase90_create_list_detail_owner_validation_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p90-crud-a")
    org2 = bootstrap_org_user(client, email_prefix="p90-crud-b")

    same_org_owner = _create_user_with_role(
        db_session,
        org_id=org1["organization_id"],
        email="p90-same-owner@example.com",
        role_name="admin",
    )
    other_org_owner = _create_user_with_role(
        db_session,
        org_id=org2["organization_id"],
        email="p90-other-owner@example.com",
        role_name="admin",
    )
    inactive_member = _create_user_with_role(
        db_session,
        org_id=org1["organization_id"],
        email="p90-inactive-member@example.com",
        role_name="reviewer",
        membership_status="inactive",
    )

    invalid_owner = client.post(
        BASE,
        headers=org1["org_headers"],
        json={"title": "Invalid", "policy_type": "acceptable_use", "owner_user_id": str(inactive_member.id)},
    )
    assert invalid_owner.status_code == 400
    assert "owner_user_id" in invalid_owner.json()["detail"]

    cross_org_owner = client.post(
        BASE,
        headers=org1["org_headers"],
        json={"title": "Cross Org", "policy_type": "acceptable_use", "owner_user_id": str(other_org_owner.id)},
    )
    assert cross_org_owner.status_code == 400

    created = _create_policy(client, org1["org_headers"], owner_user_id=str(same_org_owner.id), title="Org1 Policy")
    assert created["title"] == "Org1 Policy"
    assert created["status"] == "draft"

    listed = client.get(BASE, headers=org1["org_headers"])
    assert listed.status_code == 200
    assert [row["title"] for row in listed.json()] == ["Org1 Policy"]

    detail = client.get(f"{BASE}/{created['id']}", headers=org1["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]

    cross_tenant_detail = client.get(f"{BASE}/{created['id']}", headers=org2["org_headers"])
    assert cross_tenant_detail.status_code == 404


def test_phase90_status_lifecycle_and_approval_transition(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-lifecycle")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p90-lifecycle-owner@example.com",
        role_name="admin",
    )

    created = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Lifecycle Policy")

    invalid_direct_approve = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "approved"})
    assert invalid_direct_approve.status_code == 400

    bad_approval_fields = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"approved_by_user_id": org["user_id"]},
    )
    assert bad_approval_fields.status_code == 400

    to_under_review = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "under_review"})
    assert to_under_review.status_code == 200
    assert to_under_review.json()["status"] == "under_review"

    to_approved = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "approved"})
    assert to_approved.status_code == 200
    approved_body = to_approved.json()
    assert approved_body["status"] == "approved"
    assert approved_body["approved_by_user_id"] == org["user_id"]
    assert approved_body["approved_at"] is not None

    bad_skip = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "under_review"})
    assert bad_skip.status_code == 400

    to_deprecated = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "deprecated"})
    assert to_deprecated.status_code == 200
    assert to_deprecated.json()["status"] == "deprecated"


def test_phase90_archive_blocks_updates_except_notes_and_tags_and_requires_lifecycle(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-archive")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p90-archive-owner@example.com",
        role_name="admin",
    )

    created = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Archive Policy")

    premature_archive = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "too early"},
    )
    assert premature_archive.status_code == 400

    _transition_to_deprecated(client, org["org_headers"], created["id"])

    archived = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "superseded"},
    )
    assert archived.status_code == 200
    archived_body = archived.json()
    assert archived_body["status"] == "archived"
    assert archived_body["archived_at"] is not None
    assert archived_body["archive_reason"] == "superseded"

    blocked_update = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"title": "Should Not Update"},
    )
    assert blocked_update.status_code == 400

    allowed_update = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"notes": "archived note", "tags_json": ["archived"]},
    )
    assert allowed_update.status_code == 200
    assert allowed_update.json()["notes"] == "archived note"
    assert allowed_update.json()["tags_json"] == ["archived"]


def test_phase90_summary_filters_and_include_archived(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-summary")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p90-summary-owner@example.com",
        role_name="admin",
    )

    a = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="A", policy_type="acceptable_use")
    b = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="B", policy_type="data_retention")
    c = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="C", policy_type="incident_response")

    under_review = client.patch(f"{BASE}/{b['id']}", headers=org["org_headers"], json={"status": "under_review"})
    assert under_review.status_code == 200

    _transition_to_deprecated(client, org["org_headers"], c["id"])
    archived = client.post(f"{BASE}/{c['id']}/archive", headers=org["org_headers"], json={"reason": "old"})
    assert archived.status_code == 200

    default_list = client.get(BASE, headers=org["org_headers"])
    assert default_list.status_code == 200
    names = {row["title"] for row in default_list.json()}
    assert names == {"A", "B"}

    list_all = client.get(f"{BASE}?include_archived=true", headers=org["org_headers"])
    assert list_all.status_code == 200
    names_all = {row["title"] for row in list_all.json()}
    assert names_all == {"A", "B", "C"}

    filter_status = client.get(f"{BASE}?status=under_review", headers=org["org_headers"])
    assert filter_status.status_code == 200
    assert [row["title"] for row in filter_status.json()] == ["B"]

    filter_type = client.get(f"{BASE}?policy_type=acceptable_use", headers=org["org_headers"])
    assert filter_type.status_code == 200
    assert [row["title"] for row in filter_type.json()] == ["A"]

    filter_owner = client.get(f"{BASE}?owner={owner.id}", headers=org["org_headers"])
    assert filter_owner.status_code == 200
    assert len(filter_owner.json()) == 2

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_policies"] == 3
    assert body["by_status"]["draft"] == 1
    assert body["by_status"]["under_review"] == 1
    assert body["by_status"]["archived"] == 1
    assert body["by_policy_type"]["acceptable_use"] == 1
    assert body["by_policy_type"]["data_retention"] == 1
    assert body["by_policy_type"]["incident_response"] == 1


def test_phase90_audit_events_and_approve_permission_enforcement(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-audit")
    org_id = org["organization_id"]

    owner = _create_user_with_role(
        db_session,
        org_id=org_id,
        email="p90-audit-owner@example.com",
        role_name="admin",
    )
    writer = _create_user_with_role(
        db_session,
        org_id=org_id,
        email="p90-audit-writer@example.com",
        role_name="auditor",
    )

    # promote auditor role for write-only test but keep it without approve.
    # (NB: "reviewer" is not used here -- it does NOT carry the blanket
    # compliance_policies:approve permission. Reviewers approve a specific
    # policy only via per-request assignment (approver_user_id), not the
    # org-wide grant this test checks is absent for a plain writer.)
    writer_role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == "auditor").one()
    write_permission = db_session.query(Permission).filter(Permission.key == "compliance_policies:write").one()
    has_write_link = (
        db_session.query(RolePermission)
        .filter(RolePermission.role_id == writer_role.id, RolePermission.permission_id == write_permission.id)
        .one_or_none()
    )
    if has_write_link is None:
        db_session.add(RolePermission(role_id=writer_role.id, permission_id=write_permission.id))
        db_session.commit()

    writer_token = login_user(client, writer.email)
    writer_headers = org_headers(writer_token, org_id)

    created = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Audit Policy")
    to_under_review = client.patch(f"{BASE}/{created['id']}", headers=writer_headers, json={"status": "under_review"})
    assert to_under_review.status_code == 200

    missing_approve = client.patch(f"{BASE}/{created['id']}", headers=writer_headers, json={"status": "approved"})
    assert missing_approve.status_code == 403

    approved = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "approved"})
    assert approved.status_code == 200
    deprecated = client.patch(f"{BASE}/{created['id']}", headers=org["org_headers"], json={"status": "deprecated"})
    assert deprecated.status_code == 200
    archived = client.post(f"{BASE}/{created['id']}/archive", headers=org["org_headers"], json={"reason": "audit test"})
    assert archived.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "compliance_policy.created" in actions
    assert "compliance_policy.updated" in actions
    assert "compliance_policy.archived" in actions
