import uuid

from app.models.audit_log import AuditLog
from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
from tests.helpers.auth_org import bootstrap_org_user, org_headers


def _create_run(
    db_session,
    *,
    org_id: str,
    requested_by_user_id: uuid.UUID,
    status: str,
    cancellation_requires_approval: bool,
    created_assignments_count: int = 0,
) -> FrameworkReviewBatchAssignmentRun:
    run = FrameworkReviewBatchAssignmentRun(
        organization_id=uuid.UUID(org_id),
        status=status,
        plan_hash=f"{uuid.uuid4().hex}{uuid.uuid4().hex}",
        confirmation_text="CONFIRM_BATCH_ASSIGNMENTS",
        requested_by_user_id=requested_by_user_id,
        cancellation_requires_approval=cancellation_requires_approval,
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


def _set_org_default(client, token: str, org_id: str, enabled: bool, reason: str) -> None:
    response = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(token, org_id),
        json={
            "batch_cancellation_requires_approval": enabled,
            "batch_cancellation_policy_reason": reason,
        },
    )
    assert response.status_code == 200


def test_phase47_endpoint_requires_reason(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner1", organization_name="P47 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    response = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": True, "reason": "  "},
    )
    assert response.status_code == 422


def test_phase47_dry_run_returns_eligible_but_mutates_nothing(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner2", organization_name="P47 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Require four-eyes default")

    eligible = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=False,
    )
    already_matching = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=True,
    )

    dry_run = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": True, "reason": "Preview only"},
    )
    assert dry_run.status_code == 200
    payload = dry_run.json()
    assert payload["dry_run"] is True
    assert payload["target_value"] is True
    assert payload["eligible_count"] == 1
    assert payload["updated_count"] == 0
    assert payload["affected_run_ids"] == [str(eligible.id)]
    assert payload["skipped_reasons"]["already_matches_target"] == 1

    db_session.refresh(eligible)
    db_session.refresh(already_matching)
    assert eligible.cancellation_requires_approval is False
    assert already_matching.cancellation_requires_approval is True

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "organization_governance_settings.applied_to_open_batch_runs" not in actions


def test_phase47_live_updates_eligible_open_runs_only(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner3", organization_name="P47 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Apply to open runs")

    eligible_1 = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=False,
    )
    eligible_2 = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="failed",
        cancellation_requires_approval=False,
    )
    applied = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="applied",
        cancellation_requires_approval=False,
    )
    cancelled = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="cancelled",
        cancellation_requires_approval=False,
    )
    with_assignments = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=False,
        created_assignments_count=1,
    )

    live = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": False, "reason": "Policy rollout"},
    )
    assert live.status_code == 200
    payload = live.json()
    assert payload["dry_run"] is False
    assert payload["target_value"] is True
    assert payload["eligible_count"] == 2
    assert payload["updated_count"] == 2
    assert set(payload["affected_run_ids"]) == {str(eligible_1.id), str(eligible_2.id)}
    assert payload["skipped_reasons"]["status_applied"] == 1
    assert payload["skipped_reasons"]["status_cancelled"] == 1
    assert payload["skipped_reasons"]["has_created_assignments"] == 1

    for row in (eligible_1, eligible_2, applied, cancelled, with_assignments):
        db_session.refresh(row)
    assert eligible_1.cancellation_requires_approval is True
    assert eligible_2.cancellation_requires_approval is True
    assert applied.cancellation_requires_approval is False
    assert cancelled.cancellation_requires_approval is False
    assert with_assignments.cancellation_requires_approval is False

    actions = [row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()]
    assert "organization_governance_settings.applied_to_open_batch_runs" in actions


def test_phase47_tenant_isolation_enforced(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner4", organization_name="P47 Org4")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner5", organization_name="P47 Org5")
    owner1 = owner1_bootstrap["access_token"]
    org2 = owner2_bootstrap["organization_id"]

    forbidden = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner1, org2),
        json={"dry_run": True, "reason": "Cross tenant should fail"},
    )
    assert forbidden.status_code == 403


def test_phase47_live_does_not_update_applied_runs(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner6", organization_name="P47 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Applied runs protected")

    applied = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="applied",
        cancellation_requires_approval=False,
    )

    live = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": False, "reason": "Apply default"},
    )
    assert live.status_code == 200
    assert live.json()["updated_count"] == 0
    assert live.json()["skipped_reasons"]["status_applied"] == 1
    db_session.refresh(applied)
    assert applied.cancellation_requires_approval is False


def test_phase47_live_does_not_update_cancelled_runs(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner7", organization_name="P47 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Cancelled runs protected")

    cancelled = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="cancelled",
        cancellation_requires_approval=False,
    )

    live = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": False, "reason": "Apply default"},
    )
    assert live.status_code == 200
    assert live.json()["updated_count"] == 0
    assert live.json()["skipped_reasons"]["status_cancelled"] == 1
    db_session.refresh(cancelled)
    assert cancelled.cancellation_requires_approval is False


def test_phase47_live_does_not_update_runs_with_created_assignments(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p47-owner8", organization_name="P47 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Created assignments protected")

    with_assignments = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=False,
        created_assignments_count=2,
    )

    live = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": False, "reason": "Apply default"},
    )
    assert live.status_code == 200
    assert live.json()["updated_count"] == 0
    assert live.json()["skipped_reasons"]["has_created_assignments"] == 1
    db_session.refresh(with_assignments)
    assert with_assignments.cancellation_requires_approval is False
