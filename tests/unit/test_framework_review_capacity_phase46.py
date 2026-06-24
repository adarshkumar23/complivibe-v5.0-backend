import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
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


def _create_user_with_membership(db_session, org_id: str, email: str, role_name: str = "reviewer") -> User:
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


def _create_batch_run_via_apply(client, db_session, owner_token: str, org_id: str, reviewer_email: str) -> dict:
    framework_id = _framework_id_by_code(client, owner_token, "EU_AI_ACT")
    _apply_starter_pack(client, owner_token, org_id)
    coverage_report_id = _persist_coverage_report(client, owner_token, org_id, framework_id)
    review_id = _start_and_complete_review(client, owner_token, org_id, framework_id, coverage_report_id)
    reviewer = _create_user_with_membership(db_session, org_id, reviewer_email, "reviewer")

    validate = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/validate",
        headers=org_headers(owner_token, org_id),
        json={
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
            "notify_assignees": False,
        },
    )
    assert validate.status_code == 200
    plan_hash = validate.json()["plan_hash"]

    apply = client.post(
        "/api/v1/framework-review-capacity/batch-assignments/apply",
        headers=org_headers(owner_token, org_id),
        json={
            "plan_hash": plan_hash,
            "confirmation_text": "CONFIRM_BATCH_ASSIGNMENTS",
            "assignments": [{"review_run_id": review_id, "assigned_to_user_id": str(reviewer.id)}],
            "notify_assignees": False,
        },
    )
    assert apply.status_code == 200
    run_id = apply.json()["run_id"]
    detail = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}",
        headers=org_headers(owner_token, org_id),
    )
    assert detail.status_code == 200
    return detail.json()


def _create_non_applied_batch_run(
    db_session,
    *,
    org_id: str,
    requested_by_user_id: uuid.UUID,
    cancellation_requires_approval: bool,
) -> FrameworkReviewBatchAssignmentRun:
    run = FrameworkReviewBatchAssignmentRun(
        organization_id=uuid.UUID(org_id),
        status="validated",
        plan_hash="a" * 64,
        confirmation_text="CONFIRM_BATCH_ASSIGNMENTS",
        requested_by_user_id=requested_by_user_id,
        cancellation_requires_approval=cancellation_requires_approval,
        total_items=0,
        created_assignments_count=0,
        skipped_items_count=0,
        failed_items_count=0,
        notify_assignees=False,
        validation_report_json={"items": []},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_phase46_get_governance_settings_returns_defaults(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner1", organization_name="P46 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    response = client.get("/api/v1/organizations/me/governance-settings", headers=org_headers(owner, org))
    assert response.status_code == 200
    payload = response.json()
    assert payload["batch_cancellation_requires_approval"] is False
    assert payload["batch_cancellation_policy_reason"] is None
    assert payload["updated_by_user_id"] is None
    assert payload["updated_at"] is None


def test_phase46_enabling_requires_reason(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner2", organization_name="P46 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    response = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={"batch_cancellation_requires_approval": True},
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "batch_cancellation_policy_reason is required when changing batch_cancellation_requires_approval"
    )


def test_phase46_disabling_requires_reason(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner3", organization_name="P46 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    enabled = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "High-control mode enabled",
        },
    )
    assert enabled.status_code == 200

    disabled = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={"batch_cancellation_requires_approval": False},
    )
    assert disabled.status_code == 400
    assert (
        disabled.json()["detail"]
        == "batch_cancellation_policy_reason is required when changing batch_cancellation_requires_approval"
    )


def test_phase46_update_writes_audit_log(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner4", organization_name="P46 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    updated = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "SOX control uplift",
        },
    )
    assert updated.status_code == 200
    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "organization_governance_settings.updated" in actions


def test_phase46_new_batch_run_inherits_org_default_true_and_blocks_direct_cancel(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner5", organization_name="P46 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    updated = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "Four-eyes policy",
        },
    )
    assert updated.status_code == 200

    run_detail = _create_batch_run_via_apply(client, db_session, owner, org, "p46-reviewer1@example.com")
    assert run_detail["cancellation_requires_approval"] is True

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_detail['id']}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "direct cancel should be blocked"},
    )
    assert cancelled.status_code == 400
    assert cancelled.json()["detail"] == "Cancellation requires approval. Create a cancellation request instead."


def test_phase46_new_batch_run_inherits_org_default_false_and_allows_direct_cancel(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner6", organization_name="P46 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    set_true = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "Enable first",
        },
    )
    assert set_true.status_code == 200
    set_false = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": False,
            "batch_cancellation_policy_reason": "Operational flexibility",
        },
    )
    assert set_false.status_code == 200

    run_detail = _create_batch_run_via_apply(client, db_session, owner, org, "p46-reviewer2@example.com")
    assert run_detail["cancellation_requires_approval"] is False

    requested_by_user_id = db_session.query(FrameworkReviewBatchAssignmentRun).filter_by(
        id=uuid.UUID(run_detail["id"])
    ).one().requested_by_user_id
    non_applied_run = _create_non_applied_batch_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        cancellation_requires_approval=False,
    )

    cancelled = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{non_applied_run.id}/cancel",
        headers=org_headers(owner, org),
        json={"cancellation_reason": "allowed direct cancel"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_phase46_per_run_override_still_works_independently(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner7", organization_name="P46 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    enable = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "Default four-eyes",
        },
    )
    assert enable.status_code == 200

    run_detail = _create_batch_run_via_apply(client, db_session, owner, org, "p46-reviewer3@example.com")
    run_id = run_detail["id"]
    assert run_detail["cancellation_requires_approval"] is True

    override = client.post(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/require-cancellation-approval",
        headers=org_headers(owner, org),
        json={"enabled": False},
    )
    assert override.status_code == 200
    assert override.json()["cancellation_requires_approval"] is False

    settings = client.get("/api/v1/organizations/me/governance-settings", headers=org_headers(owner, org))
    assert settings.status_code == 200
    assert settings.json()["batch_cancellation_requires_approval"] is True


def test_phase46_existing_runs_not_retroactively_changed(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner8", organization_name="P46 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    run_1 = _create_batch_run_via_apply(client, db_session, owner, org, "p46-reviewer4@example.com")
    assert run_1["cancellation_requires_approval"] is False

    enabled = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "Default changed after first run",
        },
    )
    assert enabled.status_code == 200

    detail_1 = client.get(
        f"/api/v1/framework-review-capacity/batch-assignments/runs/{run_1['id']}",
        headers=org_headers(owner, org),
    )
    assert detail_1.status_code == 200
    assert detail_1.json()["cancellation_requires_approval"] is False

    run_2 = _create_batch_run_via_apply(client, db_session, owner, org, "p46-reviewer5@example.com")
    assert run_2["cancellation_requires_approval"] is True


def test_phase46_tenant_isolation_enforced_for_org_governance_settings(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner9", organization_name="P46 Org9")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner10", organization_name="P46 Org10")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]

    forbidden_get = client.get("/api/v1/organizations/me/governance-settings", headers=org_headers(owner1, org2))
    assert forbidden_get.status_code == 403

    forbidden_patch = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner1, org2),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "Cross-tenant should fail",
        },
    )
    assert forbidden_patch.status_code == 403

    own_get = client.get("/api/v1/organizations/me/governance-settings", headers=org_headers(owner2, org2))
    assert own_get.status_code == 200


def test_phase46_new_batch_run_inherits_false_after_explicit_disable(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p46-owner11", organization_name="P46 Org11")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    enable = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": True,
            "batch_cancellation_policy_reason": "Enable",
        },
    )
    assert enable.status_code == 200
    disable = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(owner, org),
        json={
            "batch_cancellation_requires_approval": False,
            "batch_cancellation_policy_reason": "Disable",
        },
    )
    assert disable.status_code == 200

    run_detail = _create_batch_run_via_apply(client, db_session, owner, org, "p46-reviewer6@example.com")
    run = db_session.query(FrameworkReviewBatchAssignmentRun).filter_by(id=uuid.UUID(run_detail["id"])).one()
    assert run.cancellation_requires_approval is False
