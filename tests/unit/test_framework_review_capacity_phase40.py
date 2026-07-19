import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.framework_reviewer_workload_snapshot import FrameworkReviewerWorkloadSnapshot
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import auth_headers, bootstrap_org_user, login_user, org_headers

import pytest

# The framework catalogue and starter obligations used to be seeded lazily by the
# framework/obligation GET handlers -- i.e. a read endpoint that wrote rows and
# committed. Those handlers are now side-effect-free, so any test that needs the
# catalogue present must declare that dependency explicitly.
pytestmark = pytest.mark.usefixtures("seeded_reference_data")



def _framework_id_by_code(client, token: str, code: str) -> str:
    response = client.get("/api/v1/frameworks", headers=auth_headers(token))
    assert response.status_code == 200
    for item in response.json():
        if item["code"] == code:
            return item["id"]
    raise AssertionError(f"Framework {code} not found")


def _apply_starter_pack(client, token: str, org_id: str, pack_key: str = "eu_ai_act_starter") -> None:
    response = client.post(
        f"/api/v1/framework-content/packs/{pack_key}/apply",
        headers=org_headers(token, org_id),
        json={"dry_run": False, "force_update": False},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def _persist_coverage_report(client, token: str, org_id: str, framework_id: str) -> str:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/coverage-report",
        headers=org_headers(token, org_id),
        json={"persist": True},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _start_and_complete_review(client, token: str, org_id: str, framework_id: str, coverage_report_id: str) -> str:
    started = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews",
        headers=org_headers(token, org_id),
        json={
            "review_type": "internal_review",
            "target_coverage_level": "starter",
            "coverage_report_id": coverage_report_id,
            "checklist_json": {"items": [{"key": "coverage", "done": True}]},
        },
    )
    assert started.status_code == 201
    review_id = started.json()["id"]

    completed = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/complete",
        headers=org_headers(token, org_id),
        json={
            "outcome": "pass",
            "checklist_json": {"items": [{"key": "all", "done": True}]},
            "findings_json": {"notes": "ready"},
        },
    )
    assert completed.status_code == 200
    return review_id


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


def test_phase40_capacity_permissions_seeded(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p40-owner1", organization_name="P40 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    reviewer_user = _create_active_user_with_role(db_session, org, "p40-reviewer1@example.com", "reviewer")
    auditor_user = _create_active_user_with_role(db_session, org, "p40-auditor1@example.com", "auditor")
    cm_user = _create_active_user_with_role(db_session, org, "p40-cm1@example.com", "compliance_manager")

    reviewer_token = login_user(client, reviewer_user.email, "Pass1234!@")
    auditor_token = login_user(client, auditor_user.email, "Pass1234!@")
    cm_token = login_user(client, cm_user.email, "Pass1234!@")

    reviewer_codes = set(client.get("/api/v1/auth/permissions", headers=org_headers(reviewer_token, org)).json()["permission_codes"])
    auditor_codes = set(client.get("/api/v1/auth/permissions", headers=org_headers(auditor_token, org)).json()["permission_codes"])
    cm_codes = set(client.get("/api/v1/auth/permissions", headers=org_headers(cm_token, org)).json()["permission_codes"])

    assert "framework_review_capacity:read" in reviewer_codes
    assert "framework_review_capacity:write" not in reviewer_codes
    assert "framework_review_capacity:read" in auditor_codes
    assert "framework_review_capacity:write" not in auditor_codes
    assert "framework_review_capacity:read" in cm_codes
    assert "framework_review_capacity:write" in cm_codes


def test_phase40_capacity_policy_crud_validation_and_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p40-owner2", organization_name="P40 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    invalid = client.post(
        "/api/v1/framework-review-capacity/policies",
        headers=org_headers(owner, org),
        json={
            "name": "Invalid",
            "max_active_assignments": -1,
            "max_overdue_assignments": 1,
            "status": "active",
        },
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/v1/framework-review-capacity/policies",
        headers=org_headers(owner, org),
        json={
            "name": "Reviewer Capacity",
            "role_name": "reviewer",
            "max_active_assignments": 3,
            "max_overdue_assignments": 1,
            "preferred_review_types_json": ["internal_review"],
            "preferred_target_coverage_levels_json": ["starter"],
            "status": "active",
        },
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]

    listed = client.get("/api/v1/framework-review-capacity/policies", headers=org_headers(owner, org))
    assert listed.status_code == 200
    assert any(item["id"] == policy_id for item in listed.json())

    updated = client.patch(
        f"/api/v1/framework-review-capacity/policies/{policy_id}",
        headers=org_headers(owner, org),
        json={"max_active_assignments": 5, "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["max_active_assignments"] == 5
    assert updated.json()["status"] == "inactive"

    archived = client.post(
        f"/api/v1/framework-review-capacity/policies/{policy_id}/archive",
        headers=org_headers(owner, org),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_reviewer_capacity_policy.created" in actions
    assert "framework_reviewer_capacity_policy.updated" in actions
    assert "framework_reviewer_capacity_policy.archived" in actions


def test_phase40_workload_calculation_and_persistence_tenant_scope(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p40-owner3", organization_name="P40 Org3")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p40-owner4", organization_name="P40 Org4")
    owner1 = owner1_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]

    framework_id = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    coverage_report_id = _persist_coverage_report(client, owner1, org1, framework_id)
    review_id = _start_and_complete_review(client, owner1, org1, framework_id, coverage_report_id)

    reviewer = _create_active_user_with_role(db_session, org1, "p40-reviewer2@example.com", "reviewer")
    assign = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=org_headers(owner1, org1),
        json={
            "assigned_to_user_id": str(reviewer.id),
            "due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "notify": False,
        },
    )
    assert assign.status_code == 201

    calculated = client.post(
        "/api/v1/framework-review-capacity/workload/calculate",
        headers=org_headers(owner1, org1),
        json={"persist": False},
    )
    assert calculated.status_code == 200
    payload = calculated.json()
    assert payload["count"] >= 2
    assert any(item["user_id"] == str(reviewer.id) for item in payload["snapshots"])

    persisted = client.post(
        "/api/v1/framework-review-capacity/workload/calculate",
        headers=org_headers(owner1, org1),
        json={"persist": True},
    )
    assert persisted.status_code == 200

    rows_org1 = db_session.query(FrameworkReviewerWorkloadSnapshot).filter_by(organization_id=uuid.UUID(org1)).all()
    rows_org2 = db_session.query(FrameworkReviewerWorkloadSnapshot).filter_by(organization_id=uuid.UUID(org2)).all()
    assert len(rows_org1) >= 1
    assert rows_org2 == []


def test_phase40_assignment_suggestions_apply_dismiss_summary_and_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p40-owner5", organization_name="P40 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    target_review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    backlog_review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    reviewer_a = _create_active_user_with_role(db_session, org, "p40-reviewer3@example.com", "reviewer")
    reviewer_b = _create_active_user_with_role(db_session, org, "p40-reviewer4@example.com", "reviewer")

    policy = client.post(
        "/api/v1/framework-review-capacity/policies",
        headers=org_headers(owner, org),
        json={
            "name": "Reviewer preference",
            "role_name": "reviewer",
            "max_active_assignments": 4,
            "max_overdue_assignments": 1,
            "preferred_review_types_json": ["internal_review"],
            "preferred_target_coverage_levels_json": ["starter"],
            "status": "active",
        },
    )
    assert policy.status_code == 201

    owner_me = client.get("/api/v1/auth/me", headers=auth_headers(owner)).json()
    owner_id = owner_me["id"]

    owner_backlog = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{backlog_review_id}/assignments",
        headers=org_headers(owner, org),
        json={"assigned_to_user_id": owner_id, "notify": False},
    )
    assert owner_backlog.status_code == 201

    reviewer_a_backlog = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{backlog_review_id}/assignments",
        headers=org_headers(owner, org),
        json={"assigned_to_user_id": str(reviewer_a.id), "notify": False},
    )
    assert reviewer_a_backlog.status_code == 201

    before_assignments = client.get(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{target_review_id}/assignments",
        headers=org_headers(owner, org),
    )
    assert before_assignments.status_code == 200
    assert before_assignments.json() == []

    generated = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{target_review_id}/assignment-suggestions/generate",
        headers=org_headers(owner, org),
        json={"persist": True, "limit": 5},
    )
    assert generated.status_code == 200
    assert generated.json()["persist"] is True
    assert generated.json()["count"] >= 2

    suggestions = client.get(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{target_review_id}/assignment-suggestions",
        headers=org_headers(owner, org),
    )
    assert suggestions.status_code == 200
    rows = suggestions.json()
    assert len(rows) >= 2
    assert rows[0]["score"] >= rows[1]["score"]
    assert rows[0]["suggested_user_id"] == str(reviewer_b.id)

    first_suggestion_id = rows[0]["id"]
    second_suggestion_id = rows[1]["id"]

    applied = client.post(
        f"/api/v1/framework-review-assignment-suggestions/{first_suggestion_id}/apply",
        headers=org_headers(owner, org),
        json={"notes": "apply best", "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat()},
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["created_assignment_id"]

    after_assignments = client.get(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{target_review_id}/assignments",
        headers=org_headers(owner, org),
    )
    assert after_assignments.status_code == 200
    assert len(after_assignments.json()) == 1
    assert after_assignments.json()[0]["assigned_to_user_id"] == str(reviewer_b.id)

    dismiss_missing_reason = client.post(
        f"/api/v1/framework-review-assignment-suggestions/{second_suggestion_id}/dismiss",
        headers=org_headers(owner, org),
        json={"dismissal_reason": ""},
    )
    assert dismiss_missing_reason.status_code == 400

    dismissed = client.post(
        f"/api/v1/framework-review-assignment-suggestions/{second_suggestion_id}/dismiss",
        headers=org_headers(owner, org),
        json={"dismissal_reason": "manual override"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    apply_dismissed = client.post(
        f"/api/v1/framework-review-assignment-suggestions/{second_suggestion_id}/apply",
        headers=org_headers(owner, org),
        json={"notes": "should fail"},
    )
    assert apply_dismissed.status_code == 400

    summary = client.get("/api/v1/framework-review-capacity/summary", headers=org_headers(owner, org))
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["active_reviewers"] >= 1
    assert summary_payload["total_open_assignments"] >= 1
    assert summary_payload["applied_assignment_suggestions"] >= 1

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_review_assignment_suggestions.generated" in actions
    assert "framework_review_assignment_suggestion.applied" in actions
    assert "framework_review_assignment_suggestion.dismissed" in actions
