from __future__ import annotations

import inspect
import uuid

from app.core import deps as deps_module
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from tests.helpers.auth_org import bootstrap_org_user, org_headers

BASE = "/api/v1/organizations/custom-roles"


def _create_role(client, headers: dict[str, str], *, name: str, permission_codes: list[str]) -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "name": name,
            "description": f"{name} description",
            "permission_codes": permission_codes,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_s5_p5_create_custom_role_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p5-create")
    org_id = uuid.UUID(org["organization_id"])

    role = _create_role(client, org["org_headers"], name="Risk Manager", permission_codes=["risks:read", "risks:write"])
    assert role["name"] == "Risk Manager"
    assert role["is_system_role"] is False
    assert sorted(role["permission_codes"]) == ["risks:read", "risks:write"]

    persisted = db_session.get(Role, uuid.UUID(role["id"]))
    assert persisted is not None
    assert persisted.organization_id == org_id
    assert persisted.is_system_role is False

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == org_id, AuditLog.action == "custom_role.created")
        .first()
    )
    assert audit is not None


def test_s5_p5_invalid_permission_code_rejected(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p5-invalid")
    org_id = uuid.UUID(org["organization_id"])

    response = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "name": "Bad Role",
            "description": "invalid permission",
            "permission_codes": ["risks:read", "not_a_real_permission:xyz"],
        },
    )
    assert response.status_code == 422, response.text

    persisted = (
        db_session.query(Role)
        .filter(Role.organization_id == org_id, Role.name == "Bad Role")
        .first()
    )
    assert persisted is None


def test_s5_p5_assign_role_and_permission_gate(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s5p5-assign-a")
    org_b = bootstrap_org_user(client, email_prefix="s5p5-assign-b")

    # Add org_b user into org_a with a very limited default role.
    create_membership = client.post(
        "/api/v1/memberships",
        headers=org_a["org_headers"],
        json={
            "email": org_b["email"],
            "full_name": "Cross User",
            "role_name": "readonly",
        },
    )
    assert create_membership.status_code == 201, create_membership.text
    membership_id = create_membership.json()["id"]

    role = _create_role(client, org_a["org_headers"], name="Risk Reader", permission_codes=["risks:read"])

    assign = client.post(
        f"/api/v1/organizations/memberships/{membership_id}/assign-role",
        headers=org_a["org_headers"],
        json={"role_id": role["id"]},
    )
    assert assign.status_code == 200, assign.text

    # Membership now points to custom role.
    row = db_session.get(Membership, uuid.UUID(membership_id))
    assert row is not None
    assert str(row.role_id) == role["id"]

    # Permission-gated endpoint with granted permission.
    org_b_headers_in_org_a = {
        "Authorization": f"Bearer {org_b['access_token']}",
        "X-Organization-ID": org_a["organization_id"],
    }

    allow = client.get("/api/v1/risks", headers=org_b_headers_in_org_a)
    assert allow.status_code == 200, allow.text

    deny = client.get("/api/v1/controls", headers=org_b_headers_in_org_a)
    assert deny.status_code == 403, deny.text


def test_s5_p5_deactivate_takes_effect_immediately_when_assigned(client):
    # Deactivating a custom role must take effect immediately for members still
    # assigned to it -- not be blocked until they're manually reassigned first
    # (that would leave an org admin unable to urgently revoke a role's access).
    # Permission checks join Role.is_active, so the assigned member should lose
    # the role's permissions on their very next request, with no re-login needed.
    org = bootstrap_org_user(client, email_prefix="s5p5-deact-block")
    other = bootstrap_org_user(client, email_prefix="s5p5-deact-block-user")

    role = _create_role(client, org["org_headers"], name="Vendor Manager", permission_codes=["vendors:read"])

    create_membership = client.post(
        "/api/v1/memberships",
        headers=org["org_headers"],
        json={
            "email": other["email"],
            "full_name": "Other User",
            "role_name": "readonly",
        },
    )
    assert create_membership.status_code == 201, create_membership.text
    target_membership_id = create_membership.json()["id"]

    assign = client.post(
        f"/api/v1/organizations/memberships/{target_membership_id}/assign-role",
        headers=org["org_headers"],
        json={"role_id": role["id"]},
    )
    assert assign.status_code == 200, assign.text

    # `other` is a member of `org`'s organization (not their own bootstrapped
    # org), so use their own access token with org's organization_id header.
    other_in_org_headers = org_headers(other["access_token"], org["organization_id"])

    before = client.get("/api/v1/compliance/vendors", headers=other_in_org_headers)
    assert before.status_code == 200, before.text

    deactivate = client.post(
        f"/api/v1/organizations/custom-roles/{role['id']}/deactivate",
        headers=org["org_headers"],
    )
    assert deactivate.status_code == 200, deactivate.text
    assert deactivate.json()["is_active"] is False

    after = client.get("/api/v1/compliance/vendors", headers=other_in_org_headers)
    assert after.status_code == 403, after.text


def test_s5_p5_deactivate_no_assignments_succeeds_and_system_role_protected(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p5-deact-ok")
    org_id = uuid.UUID(org["organization_id"])

    role = _create_role(client, org["org_headers"], name="Temp Role", permission_codes=["tasks:read"])
    deactivate = client.post(
        f"/api/v1/organizations/custom-roles/{role['id']}/deactivate",
        headers=org["org_headers"],
    )
    assert deactivate.status_code == 200, deactivate.text
    assert deactivate.json()["is_active"] is False

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == org_id, AuditLog.action == "custom_role.deactivated")
        .first()
    )
    assert audit is not None

    roles = client.get(BASE, headers=org["org_headers"])
    assert roles.status_code == 200
    system_role = next(item for item in roles.json() if item["is_system_role"] is True)

    edit_system = client.patch(
        f"/api/v1/organizations/custom-roles/{system_role['id']}",
        headers=org["org_headers"],
        json={"description": "nope"},
    )
    assert edit_system.status_code == 400, edit_system.text

    deactivate_system = client.post(
        f"/api/v1/organizations/custom-roles/{system_role['id']}/deactivate",
        headers=org["org_headers"],
    )
    assert deactivate_system.status_code == 400, deactivate_system.text


def test_s5_p5_role_update_and_assignment_audit_trail(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p5-audit-trail")
    other = bootstrap_org_user(client, email_prefix="s5p5-audit-trail-user")
    org_id = uuid.UUID(org["organization_id"])

    # Capture update before/after permission codes.
    role = _create_role(client, org["org_headers"], name="Audit Role", permission_codes=["risks:read"])
    updated = client.patch(
        f"{BASE}/{role['id']}",
        headers=org["org_headers"],
        json={"permission_codes": ["risks:read", "risks:write"]},
    )
    assert updated.status_code == 200

    update_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == org_id, AuditLog.action == "custom_role.updated")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert update_audit is not None
    assert update_audit.before_json.get("permission_codes") == ["risks:read"]
    assert update_audit.after_json.get("permission_codes") == ["risks:read", "risks:write"]

    # Capture assignment before/after role.
    create_membership = client.post(
        "/api/v1/memberships",
        headers=org["org_headers"],
        json={"email": other["email"], "full_name": "Audit User", "role_name": "readonly"},
    )
    assert create_membership.status_code == 201
    membership_id = create_membership.json()["id"]

    assign = client.post(
        f"/api/v1/organizations/memberships/{membership_id}/assign-role",
        headers=org["org_headers"],
        json={"role_id": role["id"]},
    )
    assert assign.status_code == 200

    assign_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == org_id, AuditLog.action == "custom_role.assigned")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert assign_audit is not None
    assert assign_audit.before_json.get("role_name") == "readonly"
    assert assign_audit.after_json.get("role_name") == "Audit Role"


def test_s5_p5_list_roles_cross_org_and_signature_unchanged(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s5p5-list-a")
    org_b = bootstrap_org_user(client, email_prefix="s5p5-list-b")

    role = _create_role(client, org_a["org_headers"], name="A Risk", permission_codes=["risks:read"])

    listed = client.get(BASE, headers=org_a["org_headers"])
    assert listed.status_code == 200, listed.text
    names = {item["name"] for item in listed.json()}
    assert "A Risk" in names
    assert any(item["is_system_role"] for item in listed.json())

    get_cross = client.get(f"{BASE}/{role['id']}", headers=org_b["org_headers"])
    assert get_cross.status_code == 404, get_cross.text

    members_b = client.get("/api/v1/memberships", headers=org_b["org_headers"])
    assert members_b.status_code == 200
    membership_b = members_b.json()[0]["id"]

    assign_cross = client.post(
        f"/api/v1/organizations/memberships/{membership_b}/assign-role",
        headers=org_b["org_headers"],
        json={"role_id": role["id"]},
    )
    assert assign_cross.status_code == 404, assign_cross.text

    # Locked seam check: signature must remain exactly require_permission(permission_code: str) -> Callable[..., Membership]
    sig = inspect.signature(deps_module.require_permission)
    param = list(sig.parameters.values())[0]
    assert param.name == "permission_code"
    assert str(param.annotation) in {"<class 'str'>", 'str'}

    source_path = "app/core/deps.py"
    with open(source_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    signature_line = next(line.strip() for line in lines if line.strip().startswith("def require_permission("))
    assert signature_line == "def require_permission(permission_code: str) -> Callable[..., Membership]:"

    # Sanity check that permission catalogue is non-empty and domain:action pattern exists.
    keys = [k for (k,) in db_session.query(Permission.key).all()]
    assert any(":" in key for key in keys)
