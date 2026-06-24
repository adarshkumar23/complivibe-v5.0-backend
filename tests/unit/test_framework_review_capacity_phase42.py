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


def test_phase42_wave_simulation_validates_org_scoped_review_ids(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p42-owner1", organization_name="P42 Org1")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p42-owner2", organization_name="P42 Org2")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    coverage_report_id = _persist_coverage_report(client, owner1, org1, framework_id)
    review_id = _start_and_complete_review(client, owner1, org1, framework_id, coverage_report_id)

    cross_org = client.post(
        "/api/v1/framework-review-capacity/simulations/review-waves",
        headers=org_headers(owner2, org2),
        json={"review_ids": [review_id], "max_waves": 1, "max_reviews_per_wave": 1},
    )
    assert cross_org.status_code == 404


def test_phase42_wave_simulation_waves_capacity_progression_no_persistence_and_audit(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p42-owner3", organization_name="P42 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_1 = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    review_2 = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    reviewer = _create_active_user_with_role(db_session, org, "p42-reviewer1@example.com", "reviewer")

    policy = client.post(
        "/api/v1/framework-review-capacity/policies",
        headers=org_headers(owner, org),
        json={
            "name": "Tight reviewer cap",
            "role_name": "reviewer",
            "max_active_assignments": 1,
            "max_overdue_assignments": 1,
            "preferred_review_types_json": ["internal_review"],
            "preferred_target_coverage_levels_json": ["starter"],
            "status": "active",
        },
    )
    assert policy.status_code == 201

    assignments_before = db_session.query(FrameworkPackReviewAssignment).filter_by(organization_id=uuid.UUID(org)).count()
    suggestions_before = (
        db_session.query(FrameworkReviewAssignmentSuggestion).filter_by(organization_id=uuid.UUID(org)).count()
    )
    snapshots_before = (
        db_session.query(FrameworkReviewerWorkloadSnapshot).filter_by(organization_id=uuid.UUID(org)).count()
    )

    simulated = client.post(
        "/api/v1/framework-review-capacity/simulations/review-waves",
        headers=org_headers(owner, org),
        json={
            "framework_id": framework_id,
            "review_ids": [review_1, review_2],
            "max_waves": 2,
            "max_reviews_per_wave": 1,
            "limit_reviewers": [str(reviewer.id)],
            "include_existing_assignments": True,
        },
    )
    assert simulated.status_code == 200
    payload = simulated.json()
    assert payload["selected_reviews_count"] == 2
    assert payload["provenance"] == "deterministic_policy_simulation_v1"
    assert "planning preview" in payload["caveat"]
    assert len(payload["waves"]) == 2
    assert len(payload["waves"][0]["planned_reviews"]) == 1
    assert payload["waves"][0]["planned_reviews"][0]["suggested_reviewer_id"] == str(reviewer.id)
    assert len(payload["waves"][1]["unassigned_in_wave"]) >= 1
    constraints = payload["waves"][1]["unassigned_in_wave"][0]["constraints_failed"]
    assert "capacity_active_full" in constraints

    assignments_after = db_session.query(FrameworkPackReviewAssignment).filter_by(organization_id=uuid.UUID(org)).count()
    suggestions_after = (
        db_session.query(FrameworkReviewAssignmentSuggestion).filter_by(organization_id=uuid.UUID(org)).count()
    )
    snapshots_after = (
        db_session.query(FrameworkReviewerWorkloadSnapshot).filter_by(organization_id=uuid.UUID(org)).count()
    )
    assert assignments_after == assignments_before
    assert suggestions_after == suggestions_before
    assert snapshots_after == snapshots_before

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_review_capacity.wave_simulation_run" in actions


def test_phase42_wave_simulation_limit_reviewers_and_unassigned_when_no_candidates(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p42-owner4", organization_name="P42 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    reviewer_a = _create_active_user_with_role(db_session, org, "p42-reviewer2@example.com", "reviewer")
    _create_active_user_with_role(db_session, org, "p42-reviewer3@example.com", "reviewer")

    limited = client.post(
        "/api/v1/framework-review-capacity/simulations/review-waves",
        headers=org_headers(owner, org),
        json={
            "review_ids": [review_id],
            "max_waves": 1,
            "max_reviews_per_wave": 5,
            "limit_reviewers": [str(reviewer_a.id)],
        },
    )
    assert limited.status_code == 200
    planned = limited.json()["waves"][0]["planned_reviews"]
    assert len(planned) == 1
    assert planned[0]["suggested_reviewer_id"] == str(reviewer_a.id)

    no_candidates = client.post(
        "/api/v1/framework-review-capacity/simulations/review-waves",
        headers=org_headers(owner, org),
        json={
            "review_ids": [review_id],
            "max_waves": 1,
            "max_reviews_per_wave": 5,
            "limit_reviewers": [str(uuid.uuid4())],
        },
    )
    assert no_candidates.status_code == 200
    unassigned = no_candidates.json()["unassigned_reviews"]
    assert len(unassigned) == 1
    assert "limit_reviewers_no_candidates" in unassigned[0]["constraints_failed"]
