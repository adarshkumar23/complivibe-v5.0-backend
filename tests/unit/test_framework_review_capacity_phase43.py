import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.email_outbox import EmailOutbox
from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_review_batch_assignment_item import FrameworkReviewBatchAssignmentItem
from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
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


def _create_user_with_membership(db_session, org_id: str, email: str, role_name: str, membership_status: str = "active") -> User:
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
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status=membership_status,
        )
    )
    db_session.commit()
    return user


def _validate_payload(assignments: list[dict], notify_assignees: bool = False) -> dict:
    return {
        "assignments": assignments,
        "notify_assignees": notify_assignees,
    }


def test_phase43_validate_explicit_plan_returns_hash_and_does_not_create_assignments(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner1", organization_name="P43 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer1@example.com", "reviewer")

    before_count = db_session.query(FrameworkPackReviewAssignment).filter_by(organization_id=uuid.UUID(org)).count()
    response = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}]),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_hash"]
    assert len(payload["plan_hash"]) == 64
    assert payload["required_confirmation_text"] == "CONFIRM_BATCH_ASSIGNMENTS"
    assert payload["total_items"] == 1
    assert payload["valid_items"] == 1
    assert "explicit confirmation" in payload["caveat"]

    after_count = db_session.query(FrameworkPackReviewAssignment).filter_by(organization_id=uuid.UUID(org)).count()
    assert after_count == before_count


def test_phase43_validate_wave_simulation_payload_returns_hash(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner2", organization_name="P43 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer2@example.com", "reviewer")

    response = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json={
            "wave_simulation_payload": {
                "review_ids": [review_id],
                "max_waves": 1,
                "max_reviews_per_wave": 5,
                "limit_reviewers": [str(reviewer.id)],
            },
            "notify_assignees": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_hash"]
    assert payload["total_items"] == 1


def test_phase43_validate_rejects_cross_tenant_review(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner3", organization_name="P43 Org3")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner4", organization_name="P43 Org4")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    coverage_report_id = _persist_coverage_report(client, owner1, org1, framework_id)
    review_id = _start_and_complete_review(client, owner1, org1, framework_id, coverage_report_id)
    reviewer2 = _create_user_with_membership(db_session, org2, "p43-reviewer3@example.com", "reviewer")

    response = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner2, org2),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer2.id)}]),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["invalid_items"] == 1
    assert "review_not_found_or_cross_tenant" in payload["validation_report"]["items"][0]["reasons"]


def test_phase43_validate_rejects_inactive_or_non_member_assignee(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner5", organization_name="P43 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    inactive = _create_user_with_membership(db_session, org, "p43-reviewer4@example.com", "reviewer", membership_status="inactive")

    response = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(inactive.id)}]),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert "assignee_not_active_org_member_or_not_eligible_for_review" in payload["validation_report"]["items"][0]["reasons"]


def test_phase43_validate_rejects_duplicate_review_item(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner6", organization_name="P43 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer1 = _create_user_with_membership(db_session, org, "p43-reviewer5@example.com", "reviewer")
    reviewer2 = _create_user_with_membership(db_session, org, "p43-reviewer6@example.com", "reviewer")

    response = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload(
            [
                {"review_run_id": review_id, "assigned_to_user_id": str(reviewer1.id)},
                {"review_run_id": review_id, "assigned_to_user_id": str(reviewer2.id)},
            ]
        ),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["invalid_items"] == 2
    assert "duplicate_review_in_request" in payload["validation_report"]["items"][0]["reasons"]


def test_phase43_apply_requires_exact_confirmation_text(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner7", organization_name="P43 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer7@example.com", "reviewer")

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}]),
    )
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner, org),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "confirm_batch_assignments",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
        },
    )
    assert apply.status_code == 400


def test_phase43_apply_rejects_plan_hash_mismatch(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner8", organization_name="P43 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer8@example.com", "reviewer")

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner, org),
        json={
            "plan_hash": "0" * 64,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
        },
    )
    assert apply.status_code == 409


def test_phase43_apply_creates_assignments_for_valid_items_and_persists_run_and_items(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner9", organization_name="P43 Org9")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_1 = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    review_2 = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer9@example.com", "reviewer")

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload(
            [
                {"review_run_id": review_1, "assigned_to_user_id": str(reviewer.id)},
                {"review_run_id": review_2, "assigned_to_user_id": str(reviewer.id)},
            ]
        ),
    )
    assert validate.status_code == 200
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner, org),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [
                {"review_run_id": review_1, "assigned_to_user_id": str(reviewer.id)},
                {"review_run_id": review_2, "assigned_to_user_id": str(reviewer.id)},
            ],
        },
    )
    assert apply.status_code == 200
    payload = apply.json()
    assert payload["created_assignments_count"] == 2
    assert payload["skipped_items_count"] == 0

    run_count = db_session.query(FrameworkReviewBatchAssignmentRun).filter_by(organization_id=uuid.UUID(org)).count()
    item_count = db_session.query(FrameworkReviewBatchAssignmentItem).filter_by(organization_id=uuid.UUID(org)).count()
    assignment_count = db_session.query(FrameworkPackReviewAssignment).filter_by(organization_id=uuid.UUID(org)).count()
    assert run_count == 1
    assert item_count == 2
    assert assignment_count == 2


def test_phase43_apply_skips_duplicate_existing_assignments(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner10", organization_name="P43 Org10")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer10@example.com", "reviewer")

    existing = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=org_headers(owner, org),
        json={"assigned_to_user_id": str(reviewer.id), "notify": False},
    )
    assert existing.status_code == 201

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}]),
    )
    assert validate.status_code == 200
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner, org),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
        },
    )
    assert apply.status_code == 200
    payload = apply.json()
    assert payload["created_assignments_count"] == 0
    assert payload["skipped_items_count"] == 1


def test_phase43_notify_assignees_queues_internal_outbox_only(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner11", organization_name="P43 Org11")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer11@example.com", "reviewer")

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}], notify_assignees=True),
    )
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner, org),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
            "notify_assignees": True,
        },
    )
    assert apply.status_code == 200

    outbox_rows = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org)).all()
    assert len(outbox_rows) == 1
    assert outbox_rows[0].event_type == "framework.review.assignment"


def test_phase43_batch_runs_list_detail_tenant_scoped_and_summary(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner12", organization_name="P43 Org12")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner13", organization_name="P43 Org13")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    coverage_report_id = _persist_coverage_report(client, owner1, org1, framework_id)
    review_id = _start_and_complete_review(client, owner1, org1, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org1, "p43-reviewer12@example.com", "reviewer")

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner1, org1),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}]),
    )
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner1, org1),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
        },
    )
    run_id = apply.json()["run_id"]

    list_own = client.get(
        "/api/v1/framework-review-capacity/batch-assignments/runs",
        headers=org_headers(owner1, org1),
    )
    assert list_own.status_code == 200
    assert len(list_own.json()) == 1

    list_other = client.get(
        "/api/v1/framework-review-capacity/batch-assignments/runs",
        headers=org_headers(owner2, org2),
    )
    assert list_other.status_code == 200
    assert list_other.json() == []

    detail_other = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}",
        headers=org_headers(owner2, org2),
    )
    assert detail_other.status_code == 404

    detail_own = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}",
        headers=org_headers(owner1, org1),
    )
    assert detail_own.status_code == 200
    assert len(detail_own.json()["items"]) == 1

    summary = client.get(
        "/api/v1/framework-review-capacity/batch-assignments/summary",
        headers=org_headers(owner1, org1),
    )
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["total_batch_runs"] == 1
    assert summary_payload["applied_batch_runs"] == 1


def test_phase43_batch_validation_and_apply_audit_logs_are_written(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p43-owner14", organization_name="P43 Org14")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p43-reviewer13@example.com", "reviewer")

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner, org),
        json=_validate_payload([{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}]),
    )
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner, org),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
        },
    )
    assert apply.status_code == 200

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_review_batch_assignment.validated" in actions
    assert "framework_review_batch_assignment.applied" in actions
