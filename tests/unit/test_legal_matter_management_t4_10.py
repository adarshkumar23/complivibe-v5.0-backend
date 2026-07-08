import uuid

import pytest

from app.models.audit_log import AuditLog
from app.models.issue import Issue
from app.models.legal_matter import LegalMatter  # noqa: F401  (ensures table registered on Base.metadata)
from app.models.permission import Permission
from app.models.risk import Risk
from app.models.role import Role
from app.models.role_permission import RolePermission
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/legal-matters"

# These are the two NEW permission codes this feature introduces. The shared
# seed_service.py PERMISSIONS dict / ROLE_PERMISSION_MAP are owned by another
# workstream and are not edited here, so this test grants them directly to the
# bootstrapped org's "owner" role via the RBAC tables so the endpoints (which
# gate on these exact codes) are reachable in this isolated test run.
_PERMISSION_CODES = ("legal_matters:read", "legal_matters:write")


@pytest.fixture(scope="session", autouse=True)
def _register_legal_matters_router(_test_app):
    from app.api.v1 import legal_matters as legal_matters_router_module

    already_mounted = any(
        getattr(route, "path", "").startswith("/api/v1/legal-matters") for route in _test_app.routes
    )
    if not already_mounted:
        _test_app.include_router(legal_matters_router_module.router, prefix="/api/v1")
    yield


def _grant_legal_matter_permissions(db_session, organization_id: str) -> None:
    org_uuid = uuid.UUID(organization_id)
    owner_role = db_session.query(Role).filter(
        Role.organization_id == org_uuid, Role.name == "owner"
    ).one()

    for code in _PERMISSION_CODES:
        permission = db_session.query(Permission).filter(Permission.key == code).one_or_none()
        if permission is None:
            permission = Permission(key=code, description=code)
            db_session.add(permission)
            db_session.flush()

        existing_link = db_session.query(RolePermission).filter(
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id == permission.id,
        ).one_or_none()
        if existing_link is None:
            db_session.add(RolePermission(role_id=owner_role.id, permission_id=permission.id))

    db_session.commit()


def _bootstrap(client, db_session, prefix: str) -> dict:
    org = bootstrap_org_user(client, email_prefix=prefix)
    _grant_legal_matter_permissions(db_session, org["organization_id"])
    return org


def _create_risk(db_session, org_id: str, *, severity: str = "low") -> Risk:
    risk = Risk(
        organization_id=uuid.UUID(org_id),
        title="Vendor breach risk",
        category="operational",
        severity=severity,
        likelihood=1,
        impact=1,
        inherent_score=1,
        status="identified",
        treatment_strategy="undecided",
    )
    db_session.add(risk)
    db_session.commit()
    db_session.refresh(risk)
    return risk


def _create_issue(db_session, org_id: str, owner_id: str, created_by: str, *, status_value: str = "open") -> Issue:
    issue = Issue(
        organization_id=uuid.UUID(org_id),
        title="Data exposure issue",
        description="desc",
        issue_type="security_incident",
        severity="high",
        source_type="manual",
        status=status_value,
        owner_id=uuid.UUID(owner_id),
        created_by=uuid.UUID(created_by),
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    return issue


def test_create_list_get_update_happy_path(client, db_session):
    org = _bootstrap(client, db_session, "lm-happy")

    created = client.post(
        BASE,
        headers=org["org_headers"],
        json={"title": "Vendor contract dispute", "matter_type": "contract_dispute", "budget": "1000.50"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Vendor contract dispute"
    assert body["status"] == "open"
    assert body["risk_escalated_since_linked"] is False
    assert body["open_linked_issue_warning"] is None

    listed = client.get(BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client.get(f"{BASE}/{body['id']}", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]

    updated = client.patch(
        f"{BASE}/{body['id']}",
        headers=org["org_headers"],
        json={"outside_counsel": "Smith & Partners"},
    )
    assert updated.status_code == 200
    assert updated.json()["outside_counsel"] == "Smith & Partners"


def test_empty_title_returns_422(client, db_session):
    org = _bootstrap(client, db_session, "lm-empty-title")
    response = client.post(BASE, headers=org["org_headers"], json={"title": ""})
    assert response.status_code == 422


def test_negative_budget_returns_422(client, db_session):
    org = _bootstrap(client, db_session, "lm-neg-budget")
    response = client.post(BASE, headers=org["org_headers"], json={"title": "Matter", "budget": "-5.00"})
    assert response.status_code == 422


def test_link_risk_and_escalation_detection(client, db_session):
    org = _bootstrap(client, db_session, "lm-escalation")
    risk = _create_risk(db_session, org["organization_id"], severity="low")

    created = client.post(BASE, headers=org["org_headers"], json={"title": "Escalation matter"})
    matter_id = created.json()["id"]

    linked = client.post(
        f"{BASE}/{matter_id}/link-risk",
        headers=org["org_headers"],
        json={"risk_id": str(risk.id)},
    )
    assert linked.status_code == 200
    assert linked.json()["related_risk_id"] == str(risk.id)
    assert linked.json()["risk_escalated_since_linked"] is False

    risk_row = db_session.query(Risk).filter_by(id=risk.id).one()
    risk_row.severity = "critical"
    db_session.commit()

    refetched = client.get(f"{BASE}/{matter_id}", headers=org["org_headers"])
    assert refetched.status_code == 200
    assert refetched.json()["risk_escalated_since_linked"] is True


def test_close_with_open_linked_issue_requires_confirm(client, db_session):
    org = _bootstrap(client, db_session, "lm-close-issue")
    issue = _create_issue(db_session, org["organization_id"], org["user_id"], org["user_id"], status_value="investigating")

    created = client.post(BASE, headers=org["org_headers"], json={"title": "Matter with open issue"})
    matter_id = created.json()["id"]

    linked = client.post(
        f"{BASE}/{matter_id}/link-issue",
        headers=org["org_headers"],
        json={"issue_id": str(issue.id)},
    )
    assert linked.status_code == 200
    assert linked.json()["open_linked_issue_warning"] is not None

    blocked = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": False})
    assert blocked.status_code == 409

    closed = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": True})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_status_bypass_attempts_are_blocked(client, db_session):
    org = _bootstrap(client, db_session, "lm-status-bypass")
    issue = _create_issue(db_session, org["organization_id"], org["user_id"], org["user_id"], status_value="open")
    created = client.post(BASE, headers=org["org_headers"], json={"title": "Matter guarded by issue"})
    matter_id = created.json()["id"]
    linked = client.post(
        f"{BASE}/{matter_id}/link-issue",
        headers=org["org_headers"],
        json={"issue_id": str(issue.id)},
    )
    assert linked.status_code == 200

    patch_status = client.patch(
        f"{BASE}/{matter_id}",
        headers=org["org_headers"],
        json={"status": "closed"},
    )
    assert patch_status.status_code == 200
    assert patch_status.json()["status"] == "open"

    patch_mixed = client.patch(
        f"{BASE}/{matter_id}",
        headers=org["org_headers"],
        json={"status": "closed", "closed_at": "2026-01-01T00:00:00Z", "outside_counsel": "Bypass LLP"},
    )
    assert patch_mixed.status_code == 200
    assert patch_mixed.json()["status"] == "open"
    assert patch_mixed.json()["closed_at"] is None
    assert patch_mixed.json()["outside_counsel"] == "Bypass LLP"

    status_close = client.post(
        f"{BASE}/{matter_id}/status",
        headers=org["org_headers"],
        json={"new_status": "closed"},
    )
    assert status_close.status_code == 422

    blocked_close = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": False})
    assert blocked_close.status_code == 409

    closed = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": True})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    reopened = client.post(
        f"{BASE}/{matter_id}/status",
        headers=org["org_headers"],
        json={"new_status": "in_progress"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "in_progress"
    assert reopened.json()["closed_at"] is None

    first = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": True})
    second = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": True})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "closed"


def test_close_with_no_linked_issue_succeeds_without_confirm(client, db_session):
    org = _bootstrap(client, db_session, "lm-close-clean")
    created = client.post(BASE, headers=org["org_headers"], json={"title": "Clean matter"})
    matter_id = created.json()["id"]

    closed = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": False})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_link_risk_or_issue_to_closed_matter_is_rejected_until_reopened(client, db_session):
    org = _bootstrap(client, db_session, "lm-closed-link")
    risk = _create_risk(db_session, org["organization_id"])
    issue = _create_issue(db_session, org["organization_id"], org["user_id"], org["user_id"])

    created = client.post(BASE, headers=org["org_headers"], json={"title": "Soon closed matter"})
    matter_id = created.json()["id"]
    closed = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": False})
    assert closed.status_code == 200

    risk_link_attempt = client.post(
        f"{BASE}/{matter_id}/link-risk", headers=org["org_headers"], json={"risk_id": str(risk.id)}
    )
    assert risk_link_attempt.status_code == 409
    assert "closed legal matter" in risk_link_attempt.json()["detail"]

    issue_link_attempt = client.post(
        f"{BASE}/{matter_id}/link-issue", headers=org["org_headers"], json={"issue_id": str(issue.id)}
    )
    assert issue_link_attempt.status_code == 409

    row = db_session.get(LegalMatter, uuid.UUID(matter_id))
    assert row.related_risk_id is None
    assert row.related_issue_id is None

    # Reopening clears the guard.
    reopened = client.post(
        f"{BASE}/{matter_id}/status", headers=org["org_headers"], json={"new_status": "open"}
    )
    assert reopened.status_code == 200
    retried = client.post(
        f"{BASE}/{matter_id}/link-risk", headers=org["org_headers"], json={"risk_id": str(risk.id)}
    )
    assert retried.status_code == 200
    assert retried.json()["related_risk_id"] == str(risk.id)


def test_link_risk_from_different_org_returns_404(client, db_session):
    org1 = _bootstrap(client, db_session, "lm-cross-a")
    org2 = _bootstrap(client, db_session, "lm-cross-b")
    other_org_risk = _create_risk(db_session, org2["organization_id"])

    created = client.post(BASE, headers=org1["org_headers"], json={"title": "Cross org matter"})
    matter_id = created.json()["id"]

    response = client.post(
        f"{BASE}/{matter_id}/link-risk",
        headers=org1["org_headers"],
        json={"risk_id": str(other_org_risk.id)},
    )
    assert response.status_code == 404


def test_owner_user_must_be_active_member_of_same_org(client, db_session):
    org1 = _bootstrap(client, db_session, "lm-owner-a")
    org2 = _bootstrap(client, db_session, "lm-owner-b")

    create_response = client.post(
        BASE,
        headers=org1["org_headers"],
        json={"title": "Cross owner matter", "owner_user_id": org2["user_id"]},
    )
    assert create_response.status_code == 422
    assert db_session.query(LegalMatter).filter(LegalMatter.title == "Cross owner matter").one_or_none() is None

    created = client.post(
        BASE,
        headers=org1["org_headers"],
        json={"title": "Owned matter", "owner_user_id": org1["user_id"]},
    )
    assert created.status_code == 201

    patch_response = client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=org1["org_headers"],
        json={"owner_user_id": org2["user_id"]},
    )
    assert patch_response.status_code == 422
    row = db_session.get(LegalMatter, uuid.UUID(created.json()["id"]))
    assert row is not None
    assert str(row.owner_user_id) == org1["user_id"]


def test_audit_log_rows_exist_for_create_link_close(client, db_session):
    org = _bootstrap(client, db_session, "lm-audit")
    risk = _create_risk(db_session, org["organization_id"])

    created = client.post(BASE, headers=org["org_headers"], json={"title": "Audited matter"})
    matter_id = created.json()["id"]

    linked = client.post(
        f"{BASE}/{matter_id}/link-risk",
        headers=org["org_headers"],
        json={"risk_id": str(risk.id)},
    )
    assert linked.status_code == 200

    closed = client.post(f"{BASE}/{matter_id}/close", headers=org["org_headers"], json={"confirm": False})
    assert closed.status_code == 200

    actions = {
        item.action
        for item in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "legal_matter.created" in actions
    assert "legal_matter.risk_linked" in actions
    assert "legal_matter.closed" in actions
