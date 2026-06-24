import uuid

from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
from app.models.organization_governance_setting_history import OrganizationGovernanceSettingHistory
from tests.helpers.auth_org import bootstrap_org_user, org_headers


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


def test_phase48_settings_update_writes_history_row(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner1", organization_name="P48 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    _set_org_default(client, owner, org, True, "Initial policy enable")

    rows = (
        db_session.query(OrganizationGovernanceSettingHistory)
        .filter(OrganizationGovernanceSettingHistory.organization_id == uuid.UUID(org))
        .all()
    )
    assert len(rows) == 1
    assert rows[0].event_type == "settings_updated"
    assert rows[0].setting_key == "batch_cancellation_requires_approval"
    assert rows[0].reason == "Initial policy enable"


def test_phase48_history_version_increments_and_before_after_captured(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner2", organization_name="P48 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    _set_org_default(client, owner, org, True, "Enable policy")
    _set_org_default(client, owner, org, False, "Disable policy")

    history = client.get("/api/v1/organizations/me/governance-settings/history", headers=org_headers(owner, org))
    assert history.status_code == 200
    payload = history.json()
    assert len(payload) == 2
    assert payload[0]["version"] == 2
    assert payload[1]["version"] == 1
    assert payload[1]["before_json"]["batch_cancellation_requires_approval"] is False
    assert payload[1]["after_json"]["batch_cancellation_requires_approval"] is True
    assert payload[0]["before_json"]["batch_cancellation_requires_approval"] is True
    assert payload[0]["after_json"]["batch_cancellation_requires_approval"] is False


def test_phase48_apply_live_writes_rollout_history_row(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner3", organization_name="P48 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Enable default")
    eligible = _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=False,
    )

    response = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": False, "reason": "Rollout to open runs"},
    )
    assert response.status_code == 200

    rows = (
        db_session.query(OrganizationGovernanceSettingHistory)
        .filter(OrganizationGovernanceSettingHistory.organization_id == uuid.UUID(org))
        .filter(OrganizationGovernanceSettingHistory.event_type == "open_batch_runs_rollout")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].setting_key == "batch_cancellation_rollout"
    assert rows[0].affected_entity_type == "framework_review_batch_assignment_run"
    assert rows[0].affected_entity_ids_json == [str(eligible.id)]
    assert rows[0].audit_log_id is not None


def test_phase48_apply_dry_run_writes_no_rollout_history(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner4", organization_name="P48 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    requested_by_user_id = uuid.UUID(owner_bootstrap["user_id"])
    _set_org_default(client, owner, org, True, "Enable default")
    _create_run(
        db_session,
        org_id=org,
        requested_by_user_id=requested_by_user_id,
        status="validated",
        cancellation_requires_approval=False,
    )

    before_count = (
        db_session.query(OrganizationGovernanceSettingHistory)
        .filter(OrganizationGovernanceSettingHistory.organization_id == uuid.UUID(org))
        .filter(OrganizationGovernanceSettingHistory.event_type == "open_batch_runs_rollout")
        .count()
    )
    response = client.post(
        "/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs",
        headers=org_headers(owner, org),
        json={"dry_run": True, "reason": "Preview only"},
    )
    assert response.status_code == 200
    after_count = (
        db_session.query(OrganizationGovernanceSettingHistory)
        .filter(OrganizationGovernanceSettingHistory.organization_id == uuid.UUID(org))
        .filter(OrganizationGovernanceSettingHistory.event_type == "open_batch_runs_rollout")
        .count()
    )
    assert before_count == after_count == 0


def test_phase48_history_endpoint_tenant_scoped(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner5", organization_name="P48 Org5")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner6", organization_name="P48 Org6")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    _set_org_default(client, owner1, org1, True, "Enable for org1")

    forbidden = client.get("/api/v1/organizations/me/governance-settings/history", headers=org_headers(owner2, org1))
    assert forbidden.status_code == 403


def test_phase48_timeline_endpoint_returns_history_entries(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner7", organization_name="P48 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    _set_org_default(client, owner, org, True, "Enable timeline event")

    response = client.get("/api/v1/organizations/me/governance-settings/timeline", headers=org_headers(owner, org))
    assert response.status_code == 200
    payload = response.json()
    assert payload["entries"]
    assert any(item["source"] == "history" and item["event_type"] == "settings_updated" for item in payload["entries"])
    assert payload["caveat"].startswith("This governance evidence bundle is generated")


def test_phase48_history_detail_endpoint_tenant_scoped(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner8", organization_name="P48 Org8")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner9", organization_name="P48 Org9")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    _set_org_default(client, owner1, org1, True, "Detail scoping")
    history = client.get("/api/v1/organizations/me/governance-settings/history", headers=org_headers(owner1, org1))
    history_id = history.json()[0]["id"]

    forbidden = client.get(
        f"/api/v1/organizations/me/governance-settings/history/{history_id}",
        headers=org_headers(owner2, org1),
    )
    assert forbidden.status_code == 403


def test_phase48_diff_endpoint_compares_versions(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner10", organization_name="P48 Org10")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    _set_org_default(client, owner, org, True, "Enable")
    _set_org_default(client, owner, org, False, "Disable")

    response = client.get(
        "/api/v1/organizations/me/governance-settings/diff",
        headers=org_headers(owner, org),
        params={"from_version": 1, "to_version": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["from_version"] == 1
    assert payload["to_version"] == 2
    assert "batch_cancellation_requires_approval" in payload["changed_keys"]
    assert payload["entries_compared"] == 2


def test_phase48_evidence_bundle_returns_current_settings_history_and_caveat(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p48-owner11", organization_name="P48 Org11")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    _set_org_default(client, owner, org, True, "Evidence baseline")

    response = client.get("/api/v1/organizations/me/governance-settings/evidence-bundle", headers=org_headers(owner, org))
    assert response.status_code == 200
    payload = response.json()
    assert payload["current_settings"]["batch_cancellation_requires_approval"] is True
    assert len(payload["history_entries"]) >= 1
    assert "organization_governance_settings.updated" in payload["relevant_audit_action_names"]
    assert payload["caveat"].startswith("This governance evidence bundle is generated")
