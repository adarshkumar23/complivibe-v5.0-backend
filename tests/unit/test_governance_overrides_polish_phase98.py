from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.export_job import ExportJob
from app.models.governance_override_request import GovernanceOverrideRequest
from app.services.governance_override_service import GovernanceOverrideService
from tests.unit.test_governance_overrides_phase32 import (
    _completed_export,
    _create_active_user_with_role,
    _create_override,
    _headers,
    _login,
    _org_id,
    _register,
)


def test_phase98_override_payload_flags_target_state_drift(client, db_session):
    owner = _register(client, "p98-owner-drift@example.com", "Pass1234!@", "P98 Override Drift")
    org = _org_id(client, owner)
    export_id, _ = _completed_export(client, owner, org)

    created = _create_override(
        client,
        owner,
        org,
        override_type="legal_hold_exception",
        target_entity_type="export_job",
        target_entity_id=export_id,
        requested_action="remove_legal_hold",
        reason="drift test",
    )
    assert created.status_code == 201
    override_id = created.json()["id"]

    service = GovernanceOverrideService(db_session)
    row = db_session.get(GovernanceOverrideRequest, uuid.UUID(override_id))
    assert row is not None
    baseline = service.collect_target_facts(
        organization_id=uuid.UUID(org),
        target_entity_type="export_job",
        target_entity_id=uuid.UUID(export_id),
    )
    row.routing_context_json = {
        "target_facts": baseline,
        "base_required_approvals": 2,
        "final_required_approvals": 2,
    }

    export = db_session.get(ExportJob, uuid.UUID(export_id))
    assert export is not None
    export.legal_hold = not bool(export.legal_hold)
    export.updated_at = datetime.now(UTC)
    db_session.add(row)
    db_session.add(export)
    db_session.commit()

    listed = client.get("/api/v1/governance/overrides", headers=_headers(owner, org))
    assert listed.status_code == 200
    body = next(item for item in listed.json()["requests"] if item["id"] == override_id)
    assert body["target_state_changed_since_request"] is True
    assert "target_state_changed" in body["context_flags"]


def test_phase98_override_reject_enforces_dual_control_and_role_constraints(client, db_session):
    owner = _register(client, "p98-owner-reject@example.com", "Pass1234!@", "P98 Override Reject")
    org = _org_id(client, owner)
    admin = _create_active_user_with_role(db_session, org, "p98-admin-reject@example.com", "admin")
    reviewer = _create_active_user_with_role(db_session, org, "p98-reviewer-reject@example.com", "reviewer")
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
        reason="reject guard",
    )
    assert created.status_code == 201
    override_id = created.json()["id"]

    row = db_session.get(GovernanceOverrideRequest, uuid.UUID(override_id))
    assert row is not None
    row.approver_role_names_json = ["admin"]
    db_session.add(row)
    db_session.commit()

    self_reject = client.post(
        f"/api/v1/governance/overrides/{override_id}/reject",
        headers=_headers(owner, org),
        json={"reason": "self reject"},
    )
    assert self_reject.status_code == 400

    forbidden_role = client.post(
        f"/api/v1/governance/overrides/{override_id}/reject",
        headers=_headers(reviewer_token, org),
        json={"reason": "reviewer reject"},
    )
    assert forbidden_role.status_code == 403

    allowed_admin = client.post(
        f"/api/v1/governance/overrides/{override_id}/reject",
        headers=_headers(admin_token, org),
        json={"reason": "admin reject"},
    )
    assert allowed_admin.status_code == 200
    assert allowed_admin.json()["status"] == "rejected"
    assert allowed_admin.json()["decision_count"] == 1


def test_phase98_override_list_filters_validate_choices(client):
    owner = _register(client, "p98-owner-filters@example.com", "Pass1234!@", "P98 Override Filters")
    org = _org_id(client, owner)

    bad_status = client.get("/api/v1/governance/overrides?status=not_a_status", headers=_headers(owner, org))
    assert bad_status.status_code == 400

    bad_type = client.get("/api/v1/governance/overrides?override_type=invalid_type", headers=_headers(owner, org))
    assert bad_type.status_code == 400

    bad_target = client.get("/api/v1/governance/overrides?target_entity_type=invalid_target", headers=_headers(owner, org))
    assert bad_target.status_code == 400

    bad_action = client.get("/api/v1/governance/overrides?requested_action=invalid_action", headers=_headers(owner, org))
    assert bad_action.status_code == 400
