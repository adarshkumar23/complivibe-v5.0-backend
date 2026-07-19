import uuid

from app.core.security import get_password_hash
from app.models.control import Control
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User

import pytest

# The framework catalogue and starter obligations used to be seeded lazily by the
# framework/obligation GET handlers -- i.e. a read endpoint that wrote rows and
# committed. Those handlers are now side-effect-free, so any test that needs the
# catalogue present must declare that dependency explicitly.
pytestmark = pytest.mark.usefixtures("seeded_reference_data")



def _register(client, email: str, password: str, org_name: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


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


def _find_framework_with_obligations(client, token: str):
    frameworks = client.get("/api/v1/frameworks", headers=_headers(token)).json()
    for framework in frameworks:
        obligations = client.get(f"/api/v1/frameworks/{framework['id']}/obligations", headers=_headers(token)).json()
        if obligations:
            return framework, obligations[0]
    raise AssertionError("No seeded framework with obligations found")


def test_control_create_permissions_and_tenant_scoping(client, db_session):
    owner_token = _register(client, "p21-owner1@example.com", "Pass1234!@", "P21 Org1")
    owner2_token = _register(client, "p21-owner2@example.com", "Pass1234!@", "P21 Org2")

    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner_token)).json()[0]["id"]
    org2 = client.get("/api/v1/organizations/me", headers=_headers(owner2_token)).json()[0]["id"]

    cm_user = _create_active_user_with_role(db_session, org1, "p21-cm@example.com", "compliance_manager")
    readonly_user = _create_active_user_with_role(db_session, org1, "p21-readonly@example.com", "readonly")
    auditor_user = _create_active_user_with_role(db_session, org1, "p21-auditor@example.com", "auditor")

    cm_token = _login(client, cm_user.email, "Pass1234!@")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")
    auditor_token = _login(client, auditor_user.email, "Pass1234!@")

    payload = {
        "title": "Access Control Policy",
        "description": "Define access control expectations",
        "control_code": "CTRL-AC-1",
        "control_type": "policy",
        "criticality": "high",
    }

    owner_create = client.post("/api/v1/controls", headers=_headers(owner_token, org1), json=payload)
    assert owner_create.status_code == 201

    cm_create = client.post(
        "/api/v1/controls",
        headers=_headers(cm_token, org1),
        json={**payload, "title": "AI Risk Process", "control_type": "ai_governance"},
    )
    assert cm_create.status_code == 201

    ro_create = client.post("/api/v1/controls", headers=_headers(readonly_token, org1), json=payload)
    assert ro_create.status_code == 403

    auditor_create = client.post("/api/v1/controls", headers=_headers(auditor_token, org1), json=payload)
    assert auditor_create.status_code == 403

    org1_controls = client.get("/api/v1/controls", headers=_headers(owner_token, org1))
    org2_controls = client.get("/api/v1/controls", headers=_headers(owner2_token, org2))
    assert org1_controls.status_code == 200
    assert org2_controls.status_code == 200
    assert len(org1_controls.json()) >= 2
    assert org2_controls.json() == []


def test_control_owner_validation_update_archive_and_audit(client, db_session):
    owner1 = _register(client, "p21-owner3@example.com", "Pass1234!@", "P21 Org3")
    owner2 = _register(client, "p21-owner4@example.com", "Pass1234!@", "P21 Org4")
    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]
    org2 = client.get("/api/v1/organizations/me", headers=_headers(owner2)).json()[0]["id"]

    other_org_user = _create_active_user_with_role(db_session, org2, "p21-other@example.com", "admin")
    same_org_user = _create_active_user_with_role(db_session, org1, "p21-same@example.com", "admin")

    bad_owner = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={
            "title": "Incident Response",
            "control_type": "process",
            "criticality": "medium",
            "owner_user_id": str(other_org_user.id),
        },
    )
    assert bad_owner.status_code == 400

    inactive_user = _create_active_user_with_role(db_session, org1, "p21-inactive-owner@example.com", "admin")
    inactive_user.is_active = False
    inactive_user.status = "inactive"
    db_session.commit()
    inactive_owner = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={
            "title": "Inactive Owner Control",
            "control_type": "process",
            "criticality": "medium",
            "owner_user_id": str(inactive_user.id),
        },
    )
    assert inactive_owner.status_code == 400
    assert "owner_user_id" in inactive_owner.json()["detail"]
    assert (
        db_session.query(Control)
        .filter(Control.organization_id == uuid.UUID(org1), Control.owner_user_id == inactive_user.id)
        .count()
        == 0
    )

    created = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={
            "title": "Incident Response",
            "control_type": "process",
            "criticality": "medium",
            "owner_user_id": str(same_org_user.id),
        },
    )
    assert created.status_code == 201
    control_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner1, org1),
        json={"status": "in_progress", "criticality": "critical", "implementation_notes": "Started rollout"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"

    archived = client.patch(f"/api/v1/controls/{control_id}/archive", headers=_headers(owner1, org1))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1)).json()
    actions = [item["action"] for item in logs]
    assert "control.created" in actions
    assert "control.updated" in actions
    assert "control.archived" in actions


def test_control_status_transitions_enforced(client, db_session):
    owner = _register(client, "p21-transitions@example.com", "Pass1234!@", "P21 Transitions Org")
    org = client.get("/api/v1/organizations/me", headers=_headers(owner)).json()[0]["id"]

    created = client.post(
        "/api/v1/controls",
        headers=_headers(owner, org),
        json={"title": "Transition Control", "control_type": "process", "criticality": "medium"},
    )
    assert created.status_code == 201
    control_id = created.json()["id"]
    assert created.json()["status"] == "not_started"

    # Cannot skip straight to needs_review from not_started (not a valid transition).
    invalid = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner, org),
        json={"status": "needs_review"},
    )
    assert invalid.status_code == 422
    assert "not_started" in invalid.json()["detail"]
    assert "needs_review" in invalid.json()["detail"]

    # Valid forward transition still works.
    valid = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner, org),
        json={"status": "in_progress"},
    )
    assert valid.status_code == 200
    assert valid.json()["status"] == "in_progress"

    archived = client.patch(f"/api/v1/controls/{control_id}/archive", headers=_headers(owner, org))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    # Archived is terminal: cannot be revived to any other status.
    revive = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner, org),
        json={"status": "in_progress"},
    )
    assert revive.status_code == 422
    assert "archived" in revive.json()["detail"]
    assert "terminal" in revive.json()["detail"]
def test_control_owner_membership_active_flag_reflects_deactivation(client, db_session):
    owner1 = _register(client, "p21-flag-owner@example.com", "Pass1234!@", "P21 Flag Org")
    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]

    delegate = _create_active_user_with_role(db_session, org1, "p21-flag-delegate@example.com", "admin")

    created = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={
            "title": "Delegated Control",
            "control_type": "process",
            "criticality": "medium",
            "owner_user_id": str(delegate.id),
        },
    )
    assert created.status_code == 201
    control_id = created.json()["id"]
    assert created.json()["owner_membership_active"] is True

    detail = client.get(f"/api/v1/controls/{control_id}", headers=_headers(owner1, org1))
    assert detail.status_code == 200
    assert detail.json()["owner_membership_active"] is True

    listed = client.get("/api/v1/controls", headers=_headers(owner1, org1))
    by_id = {row["id"]: row for row in listed.json()}
    assert by_id[control_id]["owner_membership_active"] is True

    unowned = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={"title": "Unowned Control", "control_type": "process", "criticality": "low"},
    )
    assert unowned.status_code == 201
    assert unowned.json()["owner_membership_active"] is None

    memberships = client.get("/api/v1/memberships", headers=_headers(owner1, org1)).json()
    delegate_membership_id = next(m["id"] for m in memberships if m["user_id"] == str(delegate.id))
    deactivate_resp = client.patch(
        f"/api/v1/memberships/{delegate_membership_id}/deactivate",
        headers=_headers(owner1, org1),
    )
    assert deactivate_resp.status_code == 200

    stale_detail = client.get(f"/api/v1/controls/{control_id}", headers=_headers(owner1, org1))
    assert stale_detail.json()["owner_user_id"] == str(delegate.id)
    assert stale_detail.json()["owner_membership_active"] is False

    stale_listed = client.get("/api/v1/controls", headers=_headers(owner1, org1))
    by_id_after = {row["id"]: row for row in stale_listed.json()}
    assert by_id_after[control_id]["owner_membership_active"] is False


def test_control_detail_active_exception_flags_overdue_review(client, db_session):
    from app.models.control_exception import ControlException

    owner1 = _register(client, "p21-exc-owner@example.com", "Pass1234!@", "P21 Exception Org")
    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]

    control_resp = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={"title": "Exception Control", "control_type": "process", "criticality": "medium"},
    )
    assert control_resp.status_code == 201
    control_id = control_resp.json()["id"]

    from datetime import date, timedelta

    exception_owner = _create_active_user_with_role(db_session, org1, "p21-exc-delegate@example.com", "admin")
    approver = _create_active_user_with_role(db_session, org1, "p21-exc-approver@example.com", "admin")
    approver_token = _login(client, approver.email, "Pass1234!@")

    exception_resp = client.post(
        "/api/v1/compliance/control-exceptions",
        headers=_headers(owner1, org1),
        json={
            "control_id": control_id,
            "title": "Temporary waiver",
            "description": "Cannot meet control this quarter",
            "exception_type": "temporary",
            "risk_acceptance_reason": "Vendor migration in progress",
            "owner_user_id": str(exception_owner.id),
            "effective_date": (date.today() - timedelta(days=5)).isoformat(),
            "expiry_date": (date.today() + timedelta(days=60)).isoformat(),
        },
    )
    assert exception_resp.status_code == 201
    exception_id = exception_resp.json()["id"]
    assert exception_resp.json()["status"] == "pending_approval"

    approved = client.post(
        f"/api/v1/compliance/control-exceptions/{exception_id}/approve",
        headers=_headers(approver_token, org1),
        json={"decision_notes": "approved for testing"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"

    # Backdate review_date directly (not settable at create time in this flow) to simulate a
    # review that's now overdue.
    row = db_session.query(ControlException).filter(ControlException.id == uuid.UUID(exception_id)).one()
    row.review_date = date.today() - timedelta(days=1)
    db_session.commit()

    detail = client.get(f"/api/v1/controls/{control_id}", headers=_headers(owner1, org1))
    assert detail.status_code == 200
    active_exception = detail.json()["active_exception"]
    assert active_exception is not None
    assert active_exception["risk_acceptance_reason"] == "Vendor migration in progress"
    assert active_exception["review_overdue"] is True

    # Push review_date into the future -- no longer overdue.
    row.review_date = date.today() + timedelta(days=30)
    db_session.commit()
    detail2 = client.get(f"/api/v1/controls/{control_id}", headers=_headers(owner1, org1))
    assert detail2.json()["active_exception"]["review_overdue"] is False


def test_control_mapping_unmapping_obligation_controls_and_gap_summary(client):
    owner = _register(client, "p21-owner5@example.com", "Pass1234!@", "P21 Org5")
    org_id = client.get("/api/v1/organizations/me", headers=_headers(owner)).json()[0]["id"]

    framework, obligation = _find_framework_with_obligations(client, owner)

    control = client.post(
        "/api/v1/controls",
        headers=_headers(owner, org_id),
        json={"title": "Vendor Risk Review", "control_type": "vendor", "criticality": "high"},
    )
    assert control.status_code == 201
    control_id = control.json()["id"]

    map_without_active_framework = client.post(
        f"/api/v1/controls/{control_id}/obligations",
        headers=_headers(owner, org_id),
        json={"obligation_id": obligation["id"], "mapping_type": "supports"},
    )
    assert map_without_active_framework.status_code == 400

    activate = client.post(
        f"/api/v1/frameworks/{framework['id']}/activate",
        headers=_headers(owner, org_id),
        json={"notes": "for control mapping"},
    )
    assert activate.status_code == 200

    mapped = client.post(
        f"/api/v1/controls/{control_id}/obligations",
        headers=_headers(owner, org_id),
        json={"obligation_id": obligation["id"], "mapping_type": "satisfies", "confidence": "manual_confirmed"},
    )
    assert mapped.status_code == 200
    assert mapped.json()["status"] == "active"

    duplicate_map = client.post(
        f"/api/v1/controls/{control_id}/obligations",
        headers=_headers(owner, org_id),
        json={"obligation_id": obligation["id"], "mapping_type": "satisfies", "confidence": "manual_confirmed"},
    )
    assert duplicate_map.status_code == 200

    obligation_controls = client.get(f"/api/v1/obligations/{obligation['id']}/controls", headers=_headers(owner, org_id))
    assert obligation_controls.status_code == 200
    assert any(item["id"] == control_id for item in obligation_controls.json())

    detail = client.get(f"/api/v1/controls/{control_id}", headers=_headers(owner, org_id))
    assert detail.status_code == 200
    assert len(detail.json()["mapped_obligations"]) >= 1
    assert detail.json()["evidence_count"] == 0

    unmapped = client.delete(
        f"/api/v1/controls/{control_id}/obligations/{obligation['id']}",
        headers=_headers(owner, org_id),
    )
    assert unmapped.status_code == 200
    assert unmapped.json()["status"] == "inactive"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id)).json()
    actions = [item["action"] for item in logs]
    assert "control.obligation_mapped" in actions
    assert "control.obligation_unmapped" in actions

    summary = client.get("/api/v1/controls/gaps/summary", headers=_headers(owner, org_id))
    assert summary.status_code == 200
    body = summary.json()
    for key in [
        "total_active_obligations",
        "obligations_with_controls",
        "obligations_without_controls",
        "controls_not_started",
        "controls_in_progress",
        "controls_implemented",
        "high_criticality_open_controls",
    ]:
        assert key in body
        assert isinstance(body[key], int)


def test_control_mapping_tenant_scope(client):
    owner1 = _register(client, "p21-owner6@example.com", "Pass1234!@", "P21 Org6")
    owner2 = _register(client, "p21-owner7@example.com", "Pass1234!@", "P21 Org7")
    org1 = client.get("/api/v1/organizations/me", headers=_headers(owner1)).json()[0]["id"]
    org2 = client.get("/api/v1/organizations/me", headers=_headers(owner2)).json()[0]["id"]

    framework, obligation = _find_framework_with_obligations(client, owner1)

    activate = client.post(
        f"/api/v1/frameworks/{framework['id']}/activate",
        headers=_headers(owner1, org1),
        json={"notes": "activate"},
    )
    assert activate.status_code == 200

    control = client.post(
        "/api/v1/controls",
        headers=_headers(owner1, org1),
        json={"title": "Evidence Review", "control_type": "process", "criticality": "low"},
    )
    control_id = control.json()["id"]

    cross_tenant_map = client.post(
        f"/api/v1/controls/{control_id}/obligations",
        headers=_headers(owner2, org2),
        json={"obligation_id": obligation["id"], "mapping_type": "related"},
    )
    assert cross_tenant_map.status_code == 404
