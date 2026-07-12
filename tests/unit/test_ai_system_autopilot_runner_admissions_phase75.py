import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_runner_admission import GovernanceAutopilotRunnerAdmission
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import add_org_member, bootstrap_org_user
from tests.unit.test_ai_system_autopilot_execution_approvals_phase72 import _candidate
from tests.unit.test_ai_system_autopilot_runner_simulations_phase74 import _create_require_approval_policy
from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed

INTENTS_BASE = "/api/v1/ai-governance/autopilot/execution-intents"
APPROVALS_BASE = "/api/v1/ai-governance/autopilot/execution-approvals"
RUNNER_SIMS = "/api/v1/ai-governance/autopilot/runner-simulations"
RUNNER_ADMISSIONS = "/api/v1/ai-governance/autopilot/runner-admissions"


def _create_intent(client, headers: dict[str, str], payload: dict) -> dict:
    resp = client.post(INTENTS_BASE, headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def _create_ready_simulation(
    client, headers: dict[str, str], *, assessment_id: str, ai_system_id: str, db_session, organization_id: str
) -> dict:
    policy_id = _create_require_approval_policy(client, headers)
    intent = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment_id,
                ai_system_id=ai_system_id,
                action_type="refresh_signals",
                priority_band="high",
            ),
            "policy_id": policy_id,
        },
    )
    approval = client.post(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requests", headers=headers, json={})
    assert approval.status_code == 201
    approval_id = approval.json()["approval_id"]
    approver_headers = add_org_member(
        db_session, client, organization_id, f"p75-approver-{approval_id}@example.com"
    )
    approve = client.post(
        f"{APPROVALS_BASE}/{approval_id}/approve",
        headers=approver_headers,
        json={"decision_reason": "ready for runner dry-run"},
    )
    assert approve.status_code == 200
    sim = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/runner-simulations",
        headers=headers,
        json={"approval_id": approval_id},
    )
    assert sim.status_code == 201
    return sim.json()


def _create_blocked_simulation(client, headers: dict[str, str], *, assessment_id: str, ai_system_id: str) -> dict:
    intent = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment_id,
                ai_system_id=ai_system_id,
                action_type="create_task",
                priority_band="urgent",
            ),
        },
    )
    sim = client.post(f"{INTENTS_BASE}/{intent['intent_id']}/runner-simulations", headers=headers, json={})
    assert sim.status_code == 201
    return sim.json()


def test_phase75_runner_admission_preview_read_only_and_tenant_scoped(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p75-preview-1")
    org2 = bootstrap_org_user(client, email_prefix="p75-preview-2")
    ai, assessment, _ = _seed(client, org1["org_headers"], name="P75-Preview")
    sim = _create_ready_simulation(
        client,
        org1["org_headers"],
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org1["organization_id"],
    )

    before_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerAdmission.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    preview = client.post(
        f"{RUNNER_SIMS}/{sim['simulation_id']}/admission-preview",
        headers=org1["org_headers"],
        json={},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["simulation_id"] == sim["simulation_id"]
    assert body["would_admit"] is True
    assert body["proposed_admission_status"] == "admitted"
    assert isinstance(body["idempotency_key"], str) and body["idempotency_key"]

    cross = client.post(
        f"{RUNNER_SIMS}/{sim['simulation_id']}/admission-preview",
        headers=org2["org_headers"],
        json={},
    )
    assert cross.status_code == 404

    after_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerAdmission.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit


def test_phase75_runner_admission_create_token_idempotency_and_verify(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p75-create")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P75-Create")
    sim = _create_ready_simulation(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )

    created = client.post(f"{RUNNER_SIMS}/{sim['simulation_id']}/admissions", headers=headers, json={})
    assert created.status_code == 201
    c1 = created.json()
    assert c1["admission_status"] == "admitted"
    assert isinstance(c1.get("handoff_token"), str) and c1["handoff_token"]
    assert c1.get("handoff_token_fingerprint")

    row = db_session.get(GovernanceAutopilotRunnerAdmission, uuid.UUID(c1["admission_id"]))
    assert row is not None
    assert row.handoff_token_hash is not None
    assert row.handoff_token_hash != c1["handoff_token"]
    assert row.handoff_token_fingerprint == c1["handoff_token_fingerprint"]

    duplicate = client.post(f"{RUNNER_SIMS}/{sim['simulation_id']}/admissions", headers=headers, json={})
    assert duplicate.status_code == 201
    c2 = duplicate.json()
    assert c2["admission_id"] == c1["admission_id"]
    assert c2.get("handoff_token") is None

    verify_ok = client.post(
        f"{RUNNER_ADMISSIONS}/{c1['admission_id']}/verify-token",
        headers=headers,
        json={"handoff_token": c1["handoff_token"]},
    )
    assert verify_ok.status_code == 200
    assert verify_ok.json()["valid"] is True
    assert verify_ok.json()["expired"] is False

    verify_wrong = client.post(
        f"{RUNNER_ADMISSIONS}/{c1['admission_id']}/verify-token",
        headers=headers,
        json={"handoff_token": "wrong-token"},
    )
    assert verify_wrong.status_code == 200
    assert verify_wrong.json()["valid"] is False
    assert "token_mismatch" in verify_wrong.json()["validation_errors"]

    # Simulate token expiry and verify read-only invalidation.
    row.token_expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.flush()
    expired = client.post(
        f"{RUNNER_ADMISSIONS}/{c1['admission_id']}/verify-token",
        headers=headers,
        json={"handoff_token": c1["handoff_token"]},
    )
    assert expired.status_code == 200
    assert expired.json()["valid"] is False
    assert expired.json()["expired"] is True
    assert "token_expired" in expired.json()["validation_errors"]


def test_phase75_runner_admission_blocked_revoke_archive_summary_and_contract(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p75-block-1")
    org2 = bootstrap_org_user(client, email_prefix="p75-block-2")
    headers = org1["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P75-Blocked")

    blocked_sim = _create_blocked_simulation(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])
    blocked_create = client.post(f"{RUNNER_SIMS}/{blocked_sim['simulation_id']}/admissions", headers=headers, json={})
    assert blocked_create.status_code == 201
    blocked = blocked_create.json()
    assert blocked["admission_status"] == "blocked"
    assert blocked.get("handoff_token") is None

    detail = client.get(f"{RUNNER_ADMISSIONS}/{blocked['admission_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json().get("handoff_token") is None

    cross = client.get(f"{RUNNER_ADMISSIONS}/{blocked['admission_id']}", headers=org2["org_headers"])
    assert cross.status_code == 404

    revoke_missing_reason = client.post(f"{RUNNER_ADMISSIONS}/{blocked['admission_id']}/revoke", headers=headers, json={})
    assert revoke_missing_reason.status_code == 422

    revoked = client.post(
        f"{RUNNER_ADMISSIONS}/{blocked['admission_id']}/revoke",
        headers=headers,
        json={"revoke_reason": "manual revoke"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["admission_status"] == "revoked"

    verify_revoked = client.post(
        f"{RUNNER_ADMISSIONS}/{blocked['admission_id']}/verify-token",
        headers=headers,
        json={"handoff_token": "any"},
    )
    assert verify_revoked.status_code == 200
    assert verify_revoked.json()["valid"] is False
    assert verify_revoked.json()["admission_status"] == "revoked"

    archived = client.post(
        f"{RUNNER_ADMISSIONS}/{blocked['admission_id']}/archive",
        headers=headers,
        json={"reason": "cleanup"},
    )
    assert archived.status_code == 200
    assert archived.json()["admission_status"] == "archived"

    listed = client.get(f"{RUNNER_ADMISSIONS}?admission_status=archived", headers=headers)
    assert listed.status_code == 200
    assert any(item["admission_id"] == blocked["admission_id"] for item in listed.json())

    summary = client.get(f"{RUNNER_ADMISSIONS}/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_admissions"] >= 1
    assert "blocked_count" in sb
    assert "revoked_count" in sb

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_runner_admissions" in groups


def test_phase75_runner_admissions_no_execution_or_source_mutation_and_audit_boundaries(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p75-safety")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P75-Safety")
    sim = _create_ready_simulation(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )

    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    created = client.post(f"{RUNNER_SIMS}/{sim['simulation_id']}/admissions", headers=headers, json={})
    assert created.status_code == 201
    admission_id = created.json()["admission_id"]
    token = created.json().get("handoff_token")
    assert token

    read_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.post(f"{RUNNER_SIMS}/{sim['simulation_id']}/admission-preview", headers=headers, json={})
    _ = client.get(RUNNER_ADMISSIONS, headers=headers)
    _ = client.get(f"{RUNNER_ADMISSIONS}/{admission_id}", headers=headers)
    _ = client.post(
        f"{RUNNER_ADMISSIONS}/{admission_id}/verify-token",
        headers=headers,
        json={"handoff_token": token},
    )
    _ = client.get(f"{RUNNER_ADMISSIONS}/summary", headers=headers)
    read_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert read_after == read_before

    _ = client.post(
        f"{RUNNER_ADMISSIONS}/{admission_id}/revoke",
        headers=headers,
        json={"revoke_reason": "finalize"},
    )
    _ = client.post(
        f"{RUNNER_ADMISSIONS}/{admission_id}/archive",
        headers=headers,
        json={"reason": "archive"},
    )

    after_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    assert before_signals == after_signals
    assert before_tasks == after_tasks
    assert before_reviews == after_reviews
    assert after_audit > before_audit

    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action.like("governance_autopilot_runner_admission.%"),
            )
        ).all()
    }
    assert "governance_autopilot_runner_admission.created" in actions
    assert "governance_autopilot_runner_admission.revoked" in actions
    assert "governance_autopilot_runner_admission.archived" in actions
