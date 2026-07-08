from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_system import AISystem
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers
from tests.unit.test_guardrails_envelopes_a64_a65 import APPROVAL_BASE, SYSTEMS_BASE, _create_active_user_with_role, _create_system


def test_phase92_approval_envelope_context_and_progress_fields(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p92-envelope")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="P92 Envelope")

    approver1 = _create_active_user_with_role(db_session, org["organization_id"], "p92-approver1@example.com", role_name="admin")
    approver2 = _create_active_user_with_role(db_session, org["organization_id"], "p92-approver2@example.com", role_name="admin")

    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "staging",
            "required_approvers": [str(approver1.id), str(approver2.id), str(approver1.id)],
            "conditions": [" Security review completed ", "", "   "],
        },
    )
    assert created.status_code == 201
    body = created.json()
    envelope_id = body["id"]

    assert body["required_approvers"] == [str(approver1.id), str(approver2.id)]
    assert body["conditions"] == ["Security review completed"]
    assert body["required_approver_count"] == 2
    assert body["approvals_count"] == 0
    assert body["approval_progress_pct"] == 0.0
    assert set(body["pending_approver_ids"]) == {str(approver1.id), str(approver2.id)}
    assert body["stale_pending"] is False
    assert body["has_context_drift"] is False
    assert "missing_required_votes" in body["context_flags"]

    token1 = login_user(client, approver1.email)
    vote1 = client.post(
        f"{APPROVAL_BASE}/{envelope_id}/approve",
        headers=org_headers(token1, org["organization_id"]),
        json={"notes": "   "},
    )
    assert vote1.status_code == 200
    voted = vote1.json()
    assert voted["status"] == "pending"
    assert voted["approvals_count"] == 1
    assert voted["approval_progress_pct"] == 50.0
    assert voted["pending_approver_ids"] == [str(approver2.id)]

    vote_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "approval_envelope.vote_recorded",
            AuditLog.entity_id == uuid.UUID(envelope_id),
        )
    ).scalars().all()
    assert len(vote_audit) == 1

    envelope_row = db_session.execute(
        select(AIApprovalEnvelope).where(
            AIApprovalEnvelope.organization_id == uuid.UUID(org["organization_id"]),
            AIApprovalEnvelope.id == uuid.UUID(envelope_id),
        )
    ).scalar_one()
    envelope_row.updated_at = datetime.now(UTC) - timedelta(days=10)

    system_row = db_session.execute(
        select(AISystem).where(
            AISystem.organization_id == uuid.UUID(org["organization_id"]),
            AISystem.id == uuid.UUID(system_id),
        )
    ).scalar_one()
    system_row.deployment_status = "production"
    system_row.updated_at = datetime.now(UTC)
    db_session.add(envelope_row)
    db_session.add(system_row)
    db_session.commit()

    envelope_detail = client.get(f"{APPROVAL_BASE}/{envelope_id}", headers=org["org_headers"])
    assert envelope_detail.status_code == 200
    detail = envelope_detail.json()
    assert detail["stale_pending"] is True
    assert detail["has_context_drift"] is True
    assert detail["system_deployment_status"] == "production"
    assert "stale_pending" in detail["context_flags"]
    assert "deployment_status_drift" in detail["context_flags"]

    listed = client.get(f"{SYSTEMS_BASE}/{system_id}/approval-envelopes", headers=org["org_headers"])
    assert listed.status_code == 200
    assert listed.json()[0]["stale_pending"] is True


def test_phase92_approval_envelope_edge_validations(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p92-envelope-edge")
    org_b = bootstrap_org_user(client, email_prefix="p92-envelope-edge-b")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="P92 Envelope Edge")

    approver1 = _create_active_user_with_role(db_session, org["organization_id"], "p92-edge-approver@example.com", role_name="admin")

    empty_approvers = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "staging",
            "required_approvers": [],
            "conditions": [],
        },
    )
    assert empty_approvers.status_code == 422

    foreign_approver = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "staging",
            "required_approvers": [str(approver1.id), org_b["user_id"]],
            "conditions": [],
        },
    )
    assert foreign_approver.status_code == 422
    assert "required_approvers" in foreign_approver.json()["detail"]

    same_transition = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "development",
            "required_approvers": [str(approver1.id)],
            "conditions": [],
        },
    )
    assert same_transition.status_code == 422

    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "staging",
            "required_approvers": [str(approver1.id)],
            "conditions": [],
        },
    )
    assert created.status_code == 201

    token1 = login_user(client, approver1.email)
    bad_reject = client.post(
        f"{APPROVAL_BASE}/{created.json()['id']}/reject",
        headers=org_headers(token1, org["organization_id"]),
        json={"notes": "   "},
    )
    assert bad_reject.status_code == 422
