from copy import deepcopy
from datetime import UTC, datetime, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.export_job import ExportJob
from app.models.governance_override_request import GovernanceOverrideRequest
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
        json={"export_type": "task_execution_json", "title": "Override Export"},
    )
    assert created.status_code == 201
    export_id = created.json()["id"]
    run = client.post(f"/api/v1/exports/jobs/{export_id}/run", headers=_headers(token, org_id))
    assert run.status_code == 200
    package = client.get(f"/api/v1/exports/jobs/{export_id}/package", headers=_headers(token, org_id))
    assert package.status_code == 200
    return export_id, package.json()["package_json"]


def _create_override(
    client,
    token: str,
    org_id: str,
    *,
    override_type: str,
    target_entity_type: str,
    target_entity_id: str,
    requested_action: str,
    reason: str,
    required_approvals: int = 2,
    expires_at: str | None = None,
    metadata_json: dict | None = None,
):
    payload = {
        "override_type": override_type,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id,
        "requested_action": requested_action,
        "reason": reason,
        "required_approvals": required_approvals,
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at
    if metadata_json is not None:
        payload["metadata_json"] = metadata_json
    return client.post("/api/v1/governance/overrides", headers=_headers(token, org_id), json=payload)


def test_override_permissions_and_create_validation(client, db_session):
    owner = _register(client, "p32-owner1@example.com", "Pass1234!@", "P32 Org1")
    org = _org_id(client, owner)
    reviewer = _create_active_user_with_role(db_session, org, "p32-reviewer@example.com", "reviewer")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    perms = client.get("/api/v1/auth/permissions", headers=_headers(reviewer_token, org))
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "governance_override:read" in codes
    assert "governance_override:approve" in codes

    export_id, _ = _completed_export(client, owner, org)

    bad_type = _create_override(
        client,
        owner,
        org,
        override_type="bad",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="need",
    )
    assert bad_type.status_code == 400

    bad_action = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="bad",
        reason="need",
    )
    assert bad_action.status_code == 400

    no_reason = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="   ",
    )
    assert no_reason.status_code == 400

    owner2 = _register(client, "p32-owner2@example.com", "Pass1234!@", "P32 Org2")
    org2 = _org_id(client, owner2)
    export2_id, _ = _completed_export(client, owner2, org2)
    cross_target = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export2_id,
        requested_action="archive_locked_export",
        reason="cross-tenant",
    )
    assert cross_target.status_code == 400


def test_dual_control_approval_and_archive_locked_export_execution(client, db_session):
    owner = _register(client, "p32-owner3@example.com", "Pass1234!@", "P32 Org3")
    org = _org_id(client, owner)
    admin = _create_active_user_with_role(db_session, org, "p32-admin@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p32-reviewer2@example.com", "reviewer")
    admin_token = _login(client, admin.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    export_id, package_before = _completed_export(client, owner, org)
    apply_lock = client.post(
        f"/api/v1/exports/jobs/{export_id}/retention/apply",
        headers=_headers(owner, org),
        json={"lock_days": 5, "retention_days": 10},
    )
    assert apply_lock.status_code == 200

    created = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="Emergency governance exception",
    )
    assert created.status_code == 201
    override_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    self_approve = client.post(f"/api/v1/governance/overrides/{override_id}/approve", headers=_headers(owner, org), json={})
    assert self_approve.status_code == 400

    approve_1 = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(reviewer_token, org),
        json={"reason": "reviewed"},
    )
    assert approve_1.status_code == 200
    assert approve_1.json()["status"] == "pending"

    duplicate_approve = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(reviewer_token, org),
        json={},
    )
    assert duplicate_approve.status_code == 400

    approve_2 = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(admin_token, org),
        json={"reason": "approved"},
    )
    assert approve_2.status_code == 200
    assert approve_2.json()["status"] == "approved"

    execute = client.post(f"/api/v1/governance/overrides/{override_id}/execute", headers=_headers(admin_token, org))
    assert execute.status_code == 200
    assert execute.json()["status"] == "executed"

    export_detail = client.get(f"/api/v1/exports/jobs/{export_id}", headers=_headers(owner, org))
    assert export_detail.status_code == 200
    assert export_detail.json()["job"]["status"] == "archived"

    package_after = client.get(f"/api/v1/exports/jobs/{export_id}/package", headers=_headers(owner, org))
    assert package_after.status_code == 400  # archived no longer exposed via completed-only package endpoint

    row = db_session.query(ExportJob).filter(ExportJob.id == uuid.UUID(export_id)).one()
    assert row.package_json == package_before


def test_legal_hold_interaction_and_adjust_retention_window(client, db_session):
    owner = _register(client, "p32-owner4@example.com", "Pass1234!@", "P32 Org4")
    org = _org_id(client, owner)
    admin = _create_active_user_with_role(db_session, org, "p32-admin2@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p32-reviewer3@example.com", "reviewer")
    admin_token = _login(client, admin.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    export_id, _ = _completed_export(client, owner, org)
    client.post(f"/api/v1/exports/jobs/{export_id}/retention/apply", headers=_headers(owner, org), json={"lock_days": 5, "retention_days": 20})
    legal_hold = client.post(
        f"/api/v1/exports/jobs/{export_id}/legal-hold",
        headers=_headers(owner, org),
        json={"enabled": True, "reason": "investigation"},
    )
    assert legal_hold.status_code == 200

    archive_override = _create_override(
        client,
        owner,
        org,
        override_type="legal_hold_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="try archive under hold",
    )
    assert archive_override.status_code == 201
    archive_override_id = archive_override.json()["id"]
    client.post(f"/api/v1/governance/overrides/{archive_override_id}/approve", headers=_headers(reviewer_token, org), json={})
    client.post(f"/api/v1/governance/overrides/{archive_override_id}/approve", headers=_headers(admin_token, org), json={})
    failed_exec = client.post(f"/api/v1/governance/overrides/{archive_override_id}/execute", headers=_headers(admin_token, org))
    assert failed_exec.status_code == 400

    remove_hold = _create_override(
        client,
        owner,
        org,
        override_type="legal_hold_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="remove_legal_hold",
        reason="hold resolved",
    )
    assert remove_hold.status_code == 201
    remove_hold_id = remove_hold.json()["id"]
    client.post(f"/api/v1/governance/overrides/{remove_hold_id}/approve", headers=_headers(reviewer_token, org), json={})
    client.post(f"/api/v1/governance/overrides/{remove_hold_id}/approve", headers=_headers(admin_token, org), json={})
    remove_exec = client.post(f"/api/v1/governance/overrides/{remove_hold_id}/execute", headers=_headers(admin_token, org))
    assert remove_exec.status_code == 200

    adjust = _create_override(
        client,
        owner,
        org,
        override_type="retention_window_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="adjust_retention_window",
        reason="adjust windows",
        metadata_json={
            "locked_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "retention_until": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    assert adjust.status_code == 201
    adjust_id = adjust.json()["id"]
    client.post(f"/api/v1/governance/overrides/{adjust_id}/approve", headers=_headers(reviewer_token, org), json={})
    client.post(f"/api/v1/governance/overrides/{adjust_id}/approve", headers=_headers(admin_token, org), json={})
    adjust_exec = client.post(f"/api/v1/governance/overrides/{adjust_id}/execute", headers=_headers(admin_token, org))
    assert adjust_exec.status_code == 200
    assert adjust_exec.json()["execution_result_json"]["locked_until"] is not None


def test_reject_cancel_expire_and_revocation_after_lock(client, db_session):
    owner = _register(client, "p32-owner5@example.com", "Pass1234!@", "P32 Org5")
    org = _org_id(client, owner)
    admin = _create_active_user_with_role(db_session, org, "p32-admin3@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p32-reviewer4@example.com", "reviewer")
    admin_token = _login(client, admin.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    export_id, _ = _completed_export(client, owner, org)
    att = client.post(
        f"/api/v1/exports/jobs/{export_id}/attestations",
        headers=_headers(owner, org),
        json={"attestation_type": "internal_review", "statement": "attested"},
    )
    assert att.status_code == 201
    att_id = att.json()["id"]

    reject_req = _create_override(
        client,
        owner,
        org,
        override_type="attestation_governance_exception",
        target_entity_type="export_attestation",
        target_entity_id=att_id,
        requested_action="revoke_attestation_after_lock",
        reason="bad attestation",
    )
    rid = reject_req.json()["id"]
    bad_reject = client.post(
        f"/api/v1/governance/overrides/{rid}/reject",
        headers=_headers(reviewer_token, org),
        json={"reason": " "},
    )
    assert bad_reject.status_code == 400
    rejected = client.post(
        f"/api/v1/governance/overrides/{rid}/reject",
        headers=_headers(reviewer_token, org),
        json={"reason": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    reject_execute = client.post(f"/api/v1/governance/overrides/{rid}/execute", headers=_headers(admin_token, org))
    assert reject_execute.status_code == 400

    cancel_req = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="cancel me",
    )
    cid = cancel_req.json()["id"]
    bad_cancel = client.post(
        f"/api/v1/governance/overrides/{cid}/cancel",
        headers=_headers(owner, org),
        json={"reason": " "},
    )
    assert bad_cancel.status_code == 400
    cancelled = client.post(
        f"/api/v1/governance/overrides/{cid}/cancel",
        headers=_headers(owner, org),
        json={"reason": "not needed"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    cancel_execute = client.post(f"/api/v1/governance/overrides/{cid}/execute", headers=_headers(admin_token, org))
    assert cancel_execute.status_code == 400

    exp_req = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="will expire",
        expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    )
    exp_id = exp_req.json()["id"]
    expire_run = client.post("/api/v1/governance/overrides/expire", headers=_headers(admin_token, org))
    assert expire_run.status_code == 200
    assert expire_run.json()["expired_count"] >= 1
    expired_execute = client.post(f"/api/v1/governance/overrides/{exp_id}/execute", headers=_headers(admin_token, org))
    assert expired_execute.status_code == 400

    revoke_req = _create_override(
        client,
        owner,
        org,
        override_type="attestation_governance_exception",
        target_entity_type="export_attestation",
        target_entity_id=att_id,
        requested_action="revoke_attestation_after_lock",
        reason="revoke by override",
    )
    revoke_id = revoke_req.json()["id"]
    client.post(f"/api/v1/governance/overrides/{revoke_id}/approve", headers=_headers(reviewer_token, org), json={})
    client.post(f"/api/v1/governance/overrides/{revoke_id}/approve", headers=_headers(admin_token, org), json={})
    revoke_exec = client.post(f"/api/v1/governance/overrides/{revoke_id}/execute", headers=_headers(admin_token, org))
    assert revoke_exec.status_code == 200
    att_detail = client.get(f"/api/v1/attestations/{att_id}", headers=_headers(owner, org))
    assert att_detail.status_code == 200
    assert att_detail.json()["status"] == "revoked"


def test_override_list_detail_scope_events_audit_and_summary(client, db_session):
    owner1 = _register(client, "p32-owner6@example.com", "Pass1234!@", "P32 Org6")
    owner2 = _register(client, "p32-owner7@example.com", "Pass1234!@", "P32 Org7")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)
    admin = _create_active_user_with_role(db_session, org1, "p32-admin4@example.com", "admin")
    admin_token = _login(client, admin.email, "Pass1234!@")

    export_id, _ = _completed_export(client, owner1, org1)
    created = _create_override(
        client,
        owner1,
        org1,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="summary test",
    )
    oid = created.json()["id"]
    list_org1 = client.get("/api/v1/governance/overrides", headers=_headers(owner1, org1))
    list_org2 = client.get("/api/v1/governance/overrides", headers=_headers(owner2, org2))
    assert list_org1.status_code == 200
    assert list_org2.status_code == 200
    assert any(item["id"] == oid for item in list_org1.json()["requests"])
    assert all(item["id"] != oid for item in list_org2.json()["requests"])

    detail = client.get(f"/api/v1/governance/overrides/{oid}", headers=_headers(owner1, org1))
    assert detail.status_code == 200
    assert len(detail.json()["events"]) >= 1
    assert detail.json()["events"][0]["event_type"] == "override.created"

    client.post(f"/api/v1/governance/overrides/{oid}/approve", headers=_headers(admin_token, org1), json={"reason": "1"})
    summary = client.get("/api/v1/governance/overrides/summary", headers=_headers(owner1, org1))
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_requests"] >= 1
    assert s["pending_requests"] >= 0
    assert s["approved_requests"] >= 0

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1))
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "governance_override.created" in actions
    assert "governance_override.approved" in actions
