from copy import deepcopy
from datetime import UTC, datetime, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.export_job import ExportJob
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


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
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


def _completed_export(client, token: str, org_id: str) -> tuple[str, dict]:
    created = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(token, org_id),
        json={"export_type": "task_execution_json", "title": "Template Export"},
    )
    assert created.status_code == 201
    export_id = created.json()["id"]
    run = client.post(f"/api/v1/exports/jobs/{export_id}/run", headers=_headers(token, org_id))
    assert run.status_code == 200
    package = client.get(f"/api/v1/exports/jobs/{export_id}/package", headers=_headers(token, org_id))
    assert package.status_code == 200
    return export_id, package.json()["package_json"]


def test_template_permissions_lifecycle_and_versioning(client, db_session):
    owner = _register(client, "p33-owner1@example.com", "Pass1234!@", "P33 Org1")
    org = _org_id(client, owner)
    readonly = _create_active_user_with_role(db_session, org, "p33-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly.email, "Pass1234!@")

    perms = client.get("/api/v1/auth/permissions", headers=_headers(owner, org))
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "governance_override_template:read" in codes
    assert "governance_override_template:write" in codes

    forbidden = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(readonly_token, org),
        json={
            "name": "Readonly Create",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 2,
        },
    )
    assert forbidden.status_code == 403

    below_min = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner, org),
        json={
            "name": "Too Low",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 1,
        },
    )
    assert below_min.status_code == 422

    invalid_key = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner, org),
        json={
            "name": "Invalid Key",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 2,
            "condition_rules_json": [
                {
                    "name": "bad",
                    "conditions": [{"key": "bad_key", "operator": "equals", "value": True}],
                    "effect": {"type": "set_required_approvals", "value": 3},
                }
            ],
        },
    )
    assert invalid_key.status_code == 400

    invalid_operator = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner, org),
        json={
            "name": "Invalid Operator",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 2,
            "condition_rules_json": [
                {
                    "name": "bad-op",
                    "conditions": [{"key": "legal_hold", "operator": "contains", "value": True}],
                    "effect": {"type": "set_required_approvals", "value": 3},
                }
            ],
        },
    )
    assert invalid_operator.status_code == 400

    invalid_effect = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner, org),
        json={
            "name": "Invalid Effect",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 2,
            "condition_rules_json": [
                {
                    "name": "bad-effect",
                    "conditions": [{"key": "legal_hold", "operator": "is_true"}],
                    "effect": {"type": "bad_effect", "value": 3},
                }
            ],
        },
    )
    assert invalid_effect.status_code == 400

    created = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner, org),
        json={
            "name": "Legal Hold Removal",
            "description": "Require stronger approvals for legal hold exceptions",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 2,
            "approver_role_names_json": ["owner", "admin"],
            "condition_rules_json": [
                {
                    "name": "Legal hold requires 3 approvals",
                    "conditions": [{"key": "legal_hold", "operator": "is_true"}],
                    "effect": {"type": "set_required_approvals", "value": 3},
                }
            ],
        },
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert created.json()["version"] == 1

    versions = client.get(f"/api/v1/governance/override-templates/{template_id}/versions", headers=_headers(owner, org))
    assert versions.status_code == 200
    assert versions.json()[0]["version"] == 1

    updated = client.patch(
        f"/api/v1/governance/override-templates/{template_id}",
        headers=_headers(owner, org),
        json={"default_required_approvals": 3},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    versions_after = client.get(f"/api/v1/governance/override-templates/{template_id}/versions", headers=_headers(owner, org))
    assert versions_after.status_code == 200
    assert {item["version"] for item in versions_after.json()} == {1, 2}

    archived = client.post(f"/api/v1/governance/override-templates/{template_id}/archive", headers=_headers(owner, org))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary = client.get("/api/v1/governance/override-templates/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    assert summary.json()["total_templates"] >= 1
    assert summary.json()["archived_templates"] >= 1

    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()
    }
    assert "governance_override_template.created" in actions
    assert "governance_override_template.updated" in actions
    assert "governance_override_template.archived" in actions


def test_template_routing_and_role_restricted_approval(client, db_session):
    owner_token = _register(client, "p33-owner2@example.com", "Pass1234!@", "P33 Org2")
    org = _org_id(client, owner_token)

    requester = _create_active_user_with_role(db_session, org, "p33-cm@example.com", "compliance_manager")
    admin1 = _create_active_user_with_role(db_session, org, "p33-admin1@example.com", "admin")
    admin2 = _create_active_user_with_role(db_session, org, "p33-admin2@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p33-reviewer@example.com", "reviewer")

    requester_token = _login(client, requester.email, "Pass1234!@")
    admin1_token = _login(client, admin1.email, "Pass1234!@")
    admin2_token = _login(client, admin2.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    export_id, _ = _completed_export(client, owner_token, org)
    set_hold = client.post(
        f"/api/v1/exports/jobs/{export_id}/legal-hold",
        headers=_headers(owner_token, org),
        json={"enabled": True, "reason": "legal review"},
    )
    assert set_hold.status_code == 200

    template = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner_token, org),
        json={
            "name": "Template Routed Hold Removal",
            "override_type": "legal_hold_exception",
            "target_entity_type": "export_job",
            "requested_action": "remove_legal_hold",
            "default_required_approvals": 2,
            "approver_role_names_json": ["owner", "admin", "reviewer"],
            "condition_rules_json": [
                {
                    "name": "Legal hold requires 3 approvals",
                    "conditions": [{"key": "legal_hold", "operator": "is_true"}],
                    "effect": {"type": "set_required_approvals", "value": 3},
                },
                {
                    "name": "Restrict approvers to owner/admin",
                    "conditions": [{"key": "attestation_status", "operator": "equals", "value": "unattested"}],
                    "effect": {"type": "restrict_approver_roles", "value": ["owner", "admin"]},
                },
            ],
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    created = client.post(
        "/api/v1/governance/overrides/from-template",
        headers=_headers(requester_token, org),
        json={
            "template_id": template_id,
            "target_entity_id": export_id,
            "reason": "Exception required",
        },
    )
    assert created.status_code == 201
    payload = created.json()
    override_id = payload["id"]
    assert payload["template_id"] == template_id
    assert payload["template_version"] == 1
    assert payload["required_approvals"] == 3
    assert payload["approver_role_names_json"] == ["owner", "admin"]
    assert payload["routing_context_json"]["matched_rules"]

    routing = client.get(f"/api/v1/governance/overrides/{override_id}/routing", headers=_headers(owner_token, org))
    assert routing.status_code == 200
    assert routing.json()["required_approvals"] == 3

    bad_approve = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(reviewer_token, org),
        json={"reason": "try"},
    )
    assert bad_approve.status_code == 403

    approve1 = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(admin1_token, org),
        json={"reason": "admin1"},
    )
    assert approve1.status_code == 200
    assert approve1.json()["status"] == "pending"

    approve2 = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(admin2_token, org),
        json={"reason": "admin2"},
    )
    assert approve2.status_code == 200
    assert approve2.json()["status"] == "pending"

    approve3 = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(owner_token, org),
        json={"reason": "owner"},
    )
    assert approve3.status_code == 200
    assert approve3.json()["status"] == "approved"

    execute = client.post(f"/api/v1/governance/overrides/{override_id}/execute", headers=_headers(admin1_token, org))
    assert execute.status_code == 200
    assert execute.json()["status"] == "executed"

    export_detail = client.get(f"/api/v1/exports/jobs/{export_id}", headers=_headers(owner_token, org))
    assert export_detail.status_code == 200
    assert export_detail.json()["job"]["legal_hold"] is False

    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()
    }
    assert "governance_override.created_from_template" in actions
    assert "governance_override.approved" in actions


def test_template_scope_and_non_template_override_still_works(client, db_session):
    owner1 = _register(client, "p33-owner3@example.com", "Pass1234!@", "P33 Org3")
    org1 = _org_id(client, owner1)
    owner2 = _register(client, "p33-owner4@example.com", "Pass1234!@", "P33 Org4")
    org2 = _org_id(client, owner2)

    admin = _create_active_user_with_role(db_session, org1, "p33-admin3@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org1, "p33-reviewer2@example.com", "reviewer")
    admin_token = _login(client, admin.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    template = client.post(
        "/api/v1/governance/override-templates",
        headers=_headers(owner1, org1),
        json={
            "name": "Cross Tenant Check",
            "override_type": "export_lock_exception",
            "target_entity_type": "export_job",
            "requested_action": "archive_locked_export",
            "default_required_approvals": 2,
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    denied_versions = client.get(f"/api/v1/governance/override-templates/{template_id}/versions", headers=_headers(owner2, org2))
    assert denied_versions.status_code == 404

    export_id, package_before = _completed_export(client, owner1, org1)
    lock = client.post(
        f"/api/v1/exports/jobs/{export_id}/retention/apply",
        headers=_headers(owner1, org1),
        json={"lock_days": 5, "retention_days": 7},
    )
    assert lock.status_code == 200

    created = client.post(
        "/api/v1/governance/overrides",
        headers=_headers(owner1, org1),
        json={
            "override_type": "export_lock_exception",
            "target_entity_type": "export_job",
            "target_entity_id": export_id,
            "requested_action": "archive_locked_export",
            "reason": "non-template flow",
            "required_approvals": 2,
        },
    )
    assert created.status_code == 201
    override_id = created.json()["id"]

    client.post(f"/api/v1/governance/overrides/{override_id}/approve", headers=_headers(reviewer_token, org1), json={"reason": "r"})
    client.post(f"/api/v1/governance/overrides/{override_id}/approve", headers=_headers(admin_token, org1), json={"reason": "a"})
    executed = client.post(f"/api/v1/governance/overrides/{override_id}/execute", headers=_headers(admin_token, org1))
    assert executed.status_code == 200

    row = db_session.query(ExportJob).filter(ExportJob.id == uuid.UUID(export_id)).one()
    assert row.status == "archived"
    assert row.package_json == deepcopy(package_before)

    summary = client.get("/api/v1/governance/override-templates/summary", headers=_headers(owner1, org1))
    assert summary.status_code == 200
    assert summary.json()["total_templates"] >= 1
