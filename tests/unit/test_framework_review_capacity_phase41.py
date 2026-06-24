import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_review_assignment_suggestion import FrameworkReviewAssignmentSuggestion
from app.models.framework_reviewer_workload_snapshot import FrameworkReviewerWorkloadSnapshot
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import auth_headers, bootstrap_org_user, org_headers


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
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def test_phase41_policy_simulation_validation_comparison_no_persist_and_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p41-owner1", organization_name="P41 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    invalid = client.post(
        "/api/v1/framework-review-capacity/simulations/policy",
        headers=org_headers(owner, org),
        json={
            "role_name": "reviewer",
            "max_active_assignments": -1,
            "max_overdue_assignments": 1,
        },
    )
    assert invalid.status_code == 400

    snapshots_before = (
        db_session.query(FrameworkReviewerWorkloadSnapshot).filter_by(organization_id=uuid.UUID(org)).count()
    )
    simulated = client.post(
        "/api/v1/framework-review-capacity/simulations/policy",
        headers=org_headers(owner, org),
        json={
            "role_name": "reviewer",
            "max_active_assignments": 2,
            "max_overdue_assignments": 1,
            "preferred_review_types_json": ["internal_review"],
            "preferred_target_coverage_levels_json": ["starter"],
            "review_type": "internal_review",
            "target_coverage_level": "starter",
        },
    )
    assert simulated.status_code == 200
    payload = simulated.json()
    assert "current_summary" in payload
    assert "simulated_summary" in payload
    assert payload["provenance"] == "deterministic_policy_simulation_v1"
    assert "preview-only" in payload["caveat"]
    assert len(payload["reviewer_comparisons"]) >= 1
    assert "current_workload_score" in payload["reviewer_comparisons"][0]
    assert "simulated_workload_score" in payload["reviewer_comparisons"][0]
    assert "delta" in payload["reviewer_comparisons"][0]

    snapshots_after = (
        db_session.query(FrameworkReviewerWorkloadSnapshot).filter_by(organization_id=uuid.UUID(org)).count()
    )
    assert snapshots_after == snapshots_before

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_reviewer_capacity.simulation_run" in actions

    simulation_summary = client.get(
        "/api/v1/framework-review-capacity/simulations/summary",
        headers=org_headers(owner, org),
    )
    assert simulation_summary.status_code == 200
    assert simulation_summary.json()["simulations_last_24h"] >= 1
    assert simulation_summary.json()["simulations_last_7d"] >= 1


def test_phase41_assignment_suggestion_simulation_ranked_no_persist_no_assignments_and_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p41-owner2", organization_name="P41 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    target_review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    backlog_review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    reviewer_a = _create_active_user_with_role(db_session, org, "p41-reviewer1@example.com", "reviewer")
    reviewer_b = _create_active_user_with_role(db_session, org, "p41-reviewer2@example.com", "reviewer")

    backlog_assignment = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{backlog_review_id}/assignments",
        headers=org_headers(owner, org),
        json={"assigned_to_user_id": str(reviewer_a.id), "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat()},
    )
    assert backlog_assignment.status_code == 201

    suggestion_count_before = (
        db_session.query(FrameworkReviewAssignmentSuggestion).filter_by(organization_id=uuid.UUID(org)).count()
    )
    target_assignment_count_before = (
        db_session.query(FrameworkPackReviewAssignment)
        .filter_by(organization_id=uuid.UUID(org), review_run_id=uuid.UUID(target_review_id))
        .count()
    )

    simulated = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{target_review_id}/assignment-suggestions/simulate",
        headers=org_headers(owner, org),
        json={
            "limit": 5,
            "proposed_policy_json": {
                "role_name": "reviewer",
                "max_active_assignments": 2,
                "max_overdue_assignments": 1,
                "preferred_review_types_json": ["internal_review"],
                "preferred_target_coverage_levels_json": ["starter"],
            },
        },
    )
    assert simulated.status_code == 200
    payload = simulated.json()
    assert payload["review_id"] == target_review_id
    assert payload["provenance"] == "deterministic_policy_simulation_v1"
    assert "preview-only" in payload["caveat"]
    assert payload["proposed_policy_used"]["role_name"] == "reviewer"
    assert len(payload["simulated_suggestions"]) >= 2
    assert payload["simulated_suggestions"][0]["score"] >= payload["simulated_suggestions"][1]["score"]
    assert payload["simulated_suggestions"][0]["id"] is None
    suggested_ids = {item["suggested_user_id"] for item in payload["simulated_suggestions"]}
    assert str(reviewer_b.id) in suggested_ids

    suggestion_count_after = (
        db_session.query(FrameworkReviewAssignmentSuggestion).filter_by(organization_id=uuid.UUID(org)).count()
    )
    target_assignment_count_after = (
        db_session.query(FrameworkPackReviewAssignment)
        .filter_by(organization_id=uuid.UUID(org), review_run_id=uuid.UUID(target_review_id))
        .count()
    )
    assert suggestion_count_after == suggestion_count_before
    assert target_assignment_count_after == target_assignment_count_before

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_review_assignment_suggestions.simulated" in actions


def test_phase41_simulation_tenant_isolation(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p41-owner3", organization_name="P41 Org3")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p41-owner4", organization_name="P41 Org4")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    coverage_report_id = _persist_coverage_report(client, owner1, org1, framework_id)
    review_id = _start_and_complete_review(client, owner1, org1, framework_id, coverage_report_id)

    cross_org = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/simulate",
        headers=org_headers(owner2, org2),
        json={"limit": 3},
    )
    assert cross_org.status_code == 404
