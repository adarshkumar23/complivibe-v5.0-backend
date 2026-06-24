import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


def _owner_user_id(db_session, email: str) -> uuid.UUID:
    return db_session.query(User).filter(User.email == email).one().id


def _create_user_with_membership(db_session, org_id: str, email: str, role_name: str = "owner") -> User:
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
            status="active",
        )
    )
    db_session.commit()
    return user


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
        plan_hash="f" * 64,
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


def test_phase45_request_cancellation_requires_reason(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner1", organization_name="P45 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    response = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={},
    )
    assert response.status_code == 422


def test_phase45_request_not_allowed_for_applied_run_with_created_assignments(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner2", organization_name="P45 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]),
        status="applied",
        created_assignments_count=1,
    )

    response = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "request rollback"},
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Applied batch runs cannot be cancelled because assignments were already created. Cancel individual assignments instead."
    )


def test_phase45_cancellation_request_is_tenant_scoped(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner3", organization_name="P45 Org3")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner4", organization_name="P45 Org4")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    run = _create_run(db_session, org_id=org1, requested_by_user_id=_owner_user_id(db_session, owner1_bootstrap["email"]))

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner1, org1),
        json={"reason": "tenant one request"},
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    detail = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}",
        headers=org_headers(owner2, org2),
    )
    assert detail.status_code == 404


def test_phase45_requester_cannot_approve_own_request(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner5", organization_name="P45 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "need dual approval"},
    )
    assert created.status_code == 201

    approved = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{created.json()['id']}/approve",
        headers=org_headers(owner, org),
    )
    assert approved.status_code == 400
    assert approved.json()["detail"] == "Requester cannot approve their own cancellation request"


def test_phase45_approve_changes_status_to_approved(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner6", organization_name="P45 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    approver = _create_user_with_membership(db_session, org, "p45-approver1@example.com", "owner")
    approver_token = login_user(client, approver.email)
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "approved flow"},
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    approved = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve",
        headers=org_headers(approver_token, org),
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["status"] == "approved"
    assert payload["approved_by_user_id"] == str(approver.id)
    assert payload["approved_at"] is not None


def test_phase45_reject_requires_reason(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner7", organization_name="P45 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    approver = _create_user_with_membership(db_session, org, "p45-approver2@example.com", "owner")
    approver_token = login_user(client, approver.email)
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "rejection path"},
    )
    assert created.status_code == 201

    rejected = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{created.json()['id']}/reject",
        headers=org_headers(approver_token, org),
        json={},
    )
    assert rejected.status_code == 422


def test_phase45_execute_approved_request_cancels_run_safely(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner8", organization_name="P45 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    approver = _create_user_with_membership(db_session, org, "p45-approver3@example.com", "owner")
    executor = _create_user_with_membership(db_session, org, "p45-executor1@example.com", "owner")
    approver_token = login_user(client, approver.email)
    executor_token = login_user(client, executor.email)
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]), status="failed")

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "execute cancellation"},
    )
    request_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve",
        headers=org_headers(approver_token, org),
    )
    assert approved.status_code == 200

    executed = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/execute",
        headers=org_headers(executor_token, org),
    )
    assert executed.status_code == 200
    payload = executed.json()
    assert payload["status"] == "executed"
    assert payload["executed_by_user_id"] == str(executor.id)
    assert payload["execution_result_json"]["run_status"] == "cancelled"

    run_detail = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}",
        headers=org_headers(owner, org),
    )
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "cancelled"


def test_phase45_execute_rechecks_applied_run_protection(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner9", organization_name="P45 Org9")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    approver = _create_user_with_membership(db_session, org, "p45-approver4@example.com", "owner")
    executor = _create_user_with_membership(db_session, org, "p45-executor2@example.com", "owner")
    approver_token = login_user(client, approver.email)
    executor_token = login_user(client, executor.email)
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "will become blocked"},
    )
    request_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve",
        headers=org_headers(approver_token, org),
    )
    assert approved.status_code == 200

    run.status = "applied"
    run.created_assignments_count = 2
    db_session.add(run)
    db_session.commit()

    executed = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/execute",
        headers=org_headers(executor_token, org),
    )
    assert executed.status_code == 400
    assert (
        executed.json()["detail"]
        == "Applied batch runs cannot be cancelled because assignments were already created. Cancel individual assignments instead."
    )


def test_phase45_direct_cancel_blocked_when_approval_required(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner10", organization_name="P45 Org10")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    toggled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/require-cancellation-approval",
        headers=org_headers(owner, org),
        json={"enabled": True},
    )
    assert toggled.status_code == 200
    assert toggled.json()["cancellation_requires_approval"] is True

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "direct block check"},
    )
    assert cancelled.status_code == 400
    assert cancelled.json()["detail"] == "Cancellation requires approval. Create a cancellation request instead."


def test_phase45_direct_cancel_works_when_approval_not_required(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner11", organization_name="P45 Org11")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "still allowed"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_phase45_requirement_update_works(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner12", organization_name="P45 Org12")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    enabled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/require-cancellation-approval",
        headers=org_headers(owner, org),
        json={"enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["cancellation_requires_approval"] is True

    disabled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/require-cancellation-approval",
        headers=org_headers(owner, org),
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["cancellation_requires_approval"] is False


def test_phase45_audit_logs_are_written(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p45-owner13", organization_name="P45 Org13")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    approver = _create_user_with_membership(db_session, org, "p45-approver5@example.com", "owner")
    executor = _create_user_with_membership(db_session, org, "p45-executor3@example.com", "owner")
    approver_token = login_user(client, approver.email)
    executor_token = login_user(client, executor.email)
    run = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))

    requirement = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/require-cancellation-approval",
        headers=org_headers(owner, org),
        json={"enabled": True},
    )
    assert requirement.status_code == 200

    created = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "audit execution"},
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    approved = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve",
        headers=org_headers(approver_token, org),
    )
    assert approved.status_code == 200

    executed = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/execute",
        headers=org_headers(executor_token, org),
    )
    assert executed.status_code == 200

    run2 = _create_run(db_session, org_id=org, requested_by_user_id=_owner_user_id(db_session, owner_bootstrap["email"]))
    created2 = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run2.id}/cancellation-requests",
        headers=org_headers(owner, org),
        json={"reason": "audit rejection"},
    )
    request_id2 = created2.json()["id"]
    rejected = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id2}/reject",
        headers=org_headers(approver_token, org),
        json={"rejection_reason": "not justified"},
    )
    assert rejected.status_code == 200

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_review_batch_cancellation.requested" in actions
    assert "framework_review_batch_cancellation.approved" in actions
    assert "framework_review_batch_cancellation.rejected" in actions
    assert "framework_review_batch_cancellation.executed" in actions
    assert "framework_review_batch_cancellation.requirement_updated" in actions
