from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select

from app.models.governance_override_approval import GovernanceOverrideApproval
from app.models.governance_override_request import GovernanceOverrideRequest
from tests.unit.test_governance_overrides_phase32 import (
    _completed_export,
    _create_active_user_with_role,
    _create_override,
    _headers,
    _login,
    _org_id,
    _register,
)


def test_phase80_override_list_and_detail_include_context_intelligence(client, db_session):
    owner = _register(client, "p80-owner-list@example.com", "Pass1234!@", "P80 Override Org List")
    org = _org_id(client, owner)
    export_id, _ = _completed_export(client, owner, org)

    created = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="  needs emergency exception  ",
        expires_at=(datetime.now(UTC) + timedelta(hours=8)).isoformat(),
    )
    assert created.status_code == 201
    override_id = created.json()["id"]
    assert created.json()["reason"] == "needs emergency exception"

    row = db_session.get(GovernanceOverrideRequest, uuid.UUID(override_id))
    assert row is not None
    row.created_at = row.created_at - timedelta(hours=30)
    row.updated_at = row.created_at
    db_session.add(row)
    db_session.commit()

    listed = client.get("/api/v1/governance/overrides", headers=_headers(owner, org))
    assert listed.status_code == 200
    item = next(request for request in listed.json()["requests"] if request["id"] == override_id)
    assert item["approvals_remaining"] == 2
    assert item["request_age_hours"] >= 30
    assert item["expires_in_hours"] <= 8
    assert item["stale_pending"] is True
    assert item["last_event_at"] is not None
    assert "pending_over_24h" in item["context_flags"]
    assert "approvals_outstanding" in item["context_flags"]
    assert "expires_within_24h" in item["context_flags"]
    assert "ad_hoc_override" in item["context_flags"]

    detail = client.get(f"/api/v1/governance/overrides/{override_id}", headers=_headers(owner, org))
    assert detail.status_code == 200
    request_body = detail.json()["request"]
    assert request_body["stale_pending"] is True
    assert request_body["request_age_hours"] >= 30
    assert "pending_over_24h" in request_body["context_flags"]


def test_phase80_override_summary_adds_backlog_and_failure_context(client, db_session):
    owner = _register(client, "p80-owner-summary@example.com", "Pass1234!@", "P80 Override Org Summary")
    org = _org_id(client, owner)
    admin = _create_active_user_with_role(db_session, org, "p80-admin-summary@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p80-reviewer-summary@example.com", "reviewer")
    admin_token = _login(client, admin.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    export_id, _ = _completed_export(client, owner, org)
    hold = client.post(
        f"/api/v1/exports/jobs/{export_id}/legal-hold",
        headers=_headers(owner, org),
        json={"enabled": True, "reason": "investigation"},
    )
    assert hold.status_code == 200

    pending_expiring = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="pending expiring",
        expires_at=(datetime.now(UTC) + timedelta(hours=4)).isoformat(),
    )
    assert pending_expiring.status_code == 201
    pending_id = pending_expiring.json()["id"]
    pending_row = db_session.get(GovernanceOverrideRequest, uuid.UUID(pending_id))
    assert pending_row is not None
    pending_row.created_at = pending_row.created_at - timedelta(hours=36)
    pending_row.updated_at = pending_row.created_at
    db_session.add(pending_row)
    db_session.commit()

    approved_waiting = _create_override(
        client,
        owner,
        org,
        override_type="legal_hold_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="remove_legal_hold",
        reason="approved waiting execution",
    )
    assert approved_waiting.status_code == 201
    approved_id = approved_waiting.json()["id"]
    approve_one = client.post(
        f"/api/v1/governance/overrides/{approved_id}/approve",
        headers=_headers(reviewer_token, org),
        json={"reason": "ok"},
    )
    assert approve_one.status_code == 200
    approve_two = client.post(
        f"/api/v1/governance/overrides/{approved_id}/approve",
        headers=_headers(admin_token, org),
        json={"reason": "ok"},
    )
    assert approve_two.status_code == 200
    assert approve_two.json()["status"] == "approved"

    fail_req = _create_override(
        client,
        owner,
        org,
        override_type="legal_hold_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="expected execution failure",
    )
    assert fail_req.status_code == 201
    fail_id = fail_req.json()["id"]
    client.post(f"/api/v1/governance/overrides/{fail_id}/approve", headers=_headers(reviewer_token, org), json={"reason": "ok"})
    client.post(f"/api/v1/governance/overrides/{fail_id}/approve", headers=_headers(admin_token, org), json={"reason": "ok"})
    fail_exec = client.post(f"/api/v1/governance/overrides/{fail_id}/execute", headers=_headers(admin_token, org))
    assert fail_exec.status_code == 400

    summary = client.get("/api/v1/governance/overrides/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    s = summary.json()
    assert s["pending_expiring_within_24h"] >= 1
    assert s["approved_awaiting_execution"] >= 1
    assert s["execution_failed_last_30d"] >= 1
    assert s["oldest_pending_request_age_hours"] >= 30
    assert "stale_pending_requests" in s["context_flags"]
    assert "pending_expiring_within_24h" in s["context_flags"]
    assert "approved_waiting_execution" in s["context_flags"]
    assert "recent_execution_failures" in s["context_flags"]


def test_phase80_override_reason_normalization_for_create_approve_reject_cancel(client, db_session):
    owner = _register(client, "p80-owner-reason@example.com", "Pass1234!@", "P80 Override Org Reason")
    org = _org_id(client, owner)
    admin = _create_active_user_with_role(db_session, org, "p80-admin-reason@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p80-reviewer-reason@example.com", "reviewer")
    admin_token = _login(client, admin.email, "Pass1234!@")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")
    export_id, _ = _completed_export(client, owner, org)

    created = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="  normalized reason  ",
    )
    assert created.status_code == 201
    override_id = created.json()["id"]
    assert created.json()["reason"] == "normalized reason"
    stored = db_session.get(GovernanceOverrideRequest, uuid.UUID(override_id))
    assert stored is not None
    assert stored.reason == "normalized reason"

    approve_blank = client.post(
        f"/api/v1/governance/overrides/{override_id}/approve",
        headers=_headers(reviewer_token, org),
        json={"reason": "   "},
    )
    assert approve_blank.status_code == 200
    approval_row = db_session.execute(
        select(GovernanceOverrideApproval).where(
            GovernanceOverrideApproval.organization_id == uuid.UUID(org),
            GovernanceOverrideApproval.override_request_id == uuid.UUID(override_id),
            GovernanceOverrideApproval.approver_user_id == reviewer.id,
        )
    ).scalar_one()
    assert approval_row.reason is None

    reject_req = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="reject me",
    )
    reject_id = reject_req.json()["id"]
    rejected = client.post(
        f"/api/v1/governance/overrides/{reject_id}/reject",
        headers=_headers(admin_token, org),
        json={"reason": "  policy violation  "},
    )
    assert rejected.status_code == 200
    reject_approval = db_session.execute(
        select(GovernanceOverrideApproval).where(
            GovernanceOverrideApproval.organization_id == uuid.UUID(org),
            GovernanceOverrideApproval.override_request_id == uuid.UUID(reject_id),
            GovernanceOverrideApproval.approver_user_id == admin.id,
        )
    ).scalar_one()
    assert reject_approval.reason == "policy violation"

    cancel_req = _create_override(
        client,
        owner,
        org,
        override_type="export_lock_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="archive_locked_export",
        reason="cancel me",
    )
    cancel_id = cancel_req.json()["id"]
    cancelled = client.post(
        f"/api/v1/governance/overrides/{cancel_id}/cancel",
        headers=_headers(owner, org),
        json={"reason": "  not needed anymore  "},
    )
    assert cancelled.status_code == 200
    cancel_row = db_session.get(GovernanceOverrideRequest, uuid.UUID(cancel_id))
    assert cancel_row is not None
    assert cancel_row.cancellation_reason == "not needed anymore"
