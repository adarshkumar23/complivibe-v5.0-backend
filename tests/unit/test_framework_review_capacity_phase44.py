from datetime import UTC, datetime
import uuid

from app.models.audit_log import AuditLog
from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_review_batch_assignment_item import FrameworkReviewBatchAssignmentItem
from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.core.security import get_password_hash
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


def _owner_user_id(db_session, email: str) -> uuid.UUID:
    return db_session.query(User).filter(User.email == email).one().id


def _create_run(
    db_session,
    *,
    org_id: str,
    requested_by_user_id: uuid.UUID,
    status: str = "validated",
    created_assignments_count: int = 0,
) -> FrameworkReviewBatchAssignmentRun:
    run = FrameworkReviewBatchAssignmentRun(
        organization_id=uuid.UUID(org_id),
        status=status,
        plan_hash="a" * 64,
        confirmation_text="CONFIRM_BATCH_ASSIGNMENTS",
        requested_by_user_id=requested_by_user_id,
        total_items=0,
        created_assignments_count=created_assignments_count,
        skipped_items_count=0,
        failed_items_count=0,
        notify_assignees=False,
        validation_report_json={"items": []},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_phase44_cancel_requires_reason(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner1", organization_name="P44 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]),
    )

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={},
    )
    assert cancelled.status_code == 422


def test_phase44_cancel_is_tenant_scoped(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner2", organization_name="P44 Org2")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner3", organization_name="P44 Org3")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    run = _create_run(
        db_session,
        org_id=org1,
        requested_by_user_id=_owner_user_id(db_session, owner1_bootstrap["email"]),
    )

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner2, org2),
        json={"cancellation_reason": "wrong tenant"},
    )
    assert cancelled.status_code == 404


def test_phase44_cancel_validated_or_failed_run_works(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner4", organization_name="P44 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]),
        status="failed",
    )

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "superseded by new run"},
    )
    assert cancelled.status_code == 200
    payload = cancelled.json()
    assert payload["status"] == "cancelled"
    assert payload["cancellation_reason"] == "superseded by new run"
    assert payload["cancelled_at"] is not None


def test_phase44_cancel_already_cancelled_run_fails(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner5", organization_name="P44 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    owner_user_id = _owner_user_id(db_session, owner_bootstrap["email"])

    run = FrameworkReviewBatchAssignmentRun(
        organization_id=uuid.UUID(org),
        status="cancelled",
        plan_hash="b" * 64,
        confirmation_text="CONFIRM_BATCH_ASSIGNMENTS",
        requested_by_user_id=owner_user_id,
        cancelled_by_user_id=owner_user_id,
        cancelled_at=datetime.now(UTC),
        cancellation_reason="already done",
        cancellation_metadata_json={"cancelled_from_status": "validated"},
        total_items=0,
        created_assignments_count=0,
        skipped_items_count=0,
        failed_items_count=0,
        notify_assignees=False,
        validation_report_json={"items": []},
    )
    db_session.add(run)
    db_session.commit()

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "try again"},
    )
    assert cancelled.status_code == 400


def test_phase44_cancel_applied_run_with_created_assignments_is_blocked(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner6", organization_name="P44 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p44-reviewer1@example.com", "reviewer")

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
    run_id = apply.json()["run_id"]

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "rollback"},
    )
    assert cancelled.status_code == 400
    assert (
        cancelled.json()["detail"]
        == "Applied batch runs cannot be cancelled because assignments were already created. Cancel individual assignments instead."
    )


def test_phase44_cancellation_does_not_delete_batch_items(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner7", organization_name="P44 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org, "p44-reviewer2@example.com", "reviewer")

    run = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]),
        status="failed",
    )
    item = FrameworkReviewBatchAssignmentItem(
        organization_id=uuid.UUID(org),
        batch_run_id=run.id,
        review_run_id=uuid.UUID(review_id),
        assigned_to_user_id=reviewer.id,
        status="failed",
        error_message="seed failure",
        created_at=datetime.now(UTC),
    )
    db_session.add(item)
    db_session.commit()

    before_items = (
        db_session.query(FrameworkReviewBatchAssignmentItem)
        .filter(FrameworkReviewBatchAssignmentItem.batch_run_id == run.id)
        .count()
    )
    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "closeout"},
    )
    assert cancelled.status_code == 200

    after_items = (
        db_session.query(FrameworkReviewBatchAssignmentItem)
        .filter(FrameworkReviewBatchAssignmentItem.batch_run_id == run.id)
        .count()
    )
    assert after_items == before_items == 1


def test_phase44_cancellation_fields_in_run_detail_and_summary_includes_cancelled(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner8", organization_name="P44 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]),
        status="validated",
    )

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "operator requested stop"},
    )
    assert cancelled.status_code == 200

    detail = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}",
        headers=org_headers(owner, org),
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["status"] == "cancelled"
    assert detail_payload["cancellation_reason"] == "operator requested stop"
    assert detail_payload["cancelled_at"] is not None

    summary = client.get(
        "/api/v1/framework-review-capacity/batch-assignments/summary",
        headers=org_headers(owner, org),
    )
    assert summary.status_code == 200
    assert summary.json()["cancelled_batch_runs"] == 1


def test_phase44_cancellation_audit_log_written(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p44-owner9", organization_name="P44 Org9")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]),
    )

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "manual stop"},
    )
    assert cancelled.status_code == 200

    actions = {
        row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()
    }
    assert "framework_review_batch_assignment.cancelled" in actions
    assignment_count = db_session.query(FrameworkPackReviewAssignment).filter_by(organization_id=uuid.UUID(org)).count()
    assert assignment_count == 0
