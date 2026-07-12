import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_runner_admission import GovernanceAutopilotRunnerAdmission
from app.models.governance_autopilot_runner_handshake import GovernanceAutopilotRunnerHandshake
from app.models.governance_autopilot_runner_session import GovernanceAutopilotRunnerSession
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed
from tests.unit.test_ai_system_autopilot_runner_sessions_phase76 import (
    RUNNER_SESSIONS,
    _create_admitted_admission,
)

RUNNER_HANDSHAKE_CONTRACT = "/api/v1/ai-governance/autopilot/runner-handshake/contract"
RUNNER_HANDSHAKES = "/api/v1/ai-governance/autopilot/runner-handshakes"


def _create_session(
    client, headers: dict[str, str], *, assessment_id: str, ai_system_id: str, db_session, organization_id: str
) -> dict:
    admission = _create_admitted_admission(
        client,
        headers,
        assessment_id=assessment_id,
        ai_system_id=ai_system_id,
        db_session=db_session,
        organization_id=organization_id,
    )
    created = client.post(
        f"/api/v1/ai-governance/autopilot/runner-admissions/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": admission["handoff_token"], "replay_window_seconds": 60},
    )
    assert created.status_code == 201
    return {
        "admission": admission,
        "session": created.json(),
    }


def test_phase77_handshake_contract_preview_read_only_no_audit_no_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p77-contract")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P77-Contract")
    seeded = _create_session(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )

    contract = client.get(RUNNER_HANDSHAKE_CONTRACT, headers=headers)
    assert contract.status_code == 200
    cb = contract.json()
    assert cb["dry_run_only"] is True
    assert cb["execution_allowed"] is False
    assert "idempotency_rules" in cb

    before_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerHandshake.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    preview = client.post(
        f"{RUNNER_SESSIONS}/{seeded['session']['session_id']}/handshake-preview",
        headers=headers,
        json={},
    )
    assert preview.status_code == 200
    pb = preview.json()
    assert pb["would_create_handshake"] is True
    assert pb["proposed_handshake_status"] == "ready_for_future_runner"
    assert pb["idempotency_key"]

    after_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerHandshake.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit

    session_row = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(seeded["session"]["session_id"]))
    assert session_row is not None
    assert int(session_row.attempt_count) == 0


def test_phase77_handshake_create_verify_idempotency_and_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p77-create-1")
    org2 = bootstrap_org_user(client, email_prefix="p77-create-2")
    headers = org1["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P77-Create")
    seeded = _create_session(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org1["organization_id"],
    )
    session_id = seeded["session"]["session_id"]
    session_token = seeded["session"]["session_token"]

    wrong = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/handshakes",
        headers=headers,
        json={"session_token": "wrong-token"},
    )
    assert wrong.status_code == 400

    created = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/handshakes",
        headers=headers,
        json={"session_token": session_token, "idempotency_key": "hs-77-idem"},
    )
    assert created.status_code == 201
    c = created.json()
    assert c["handshake_status"] == "ready_for_future_runner"
    assert c["idempotency_key"] == "hs-77-idem"

    session_row = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(session_id))
    assert session_row is not None
    assert int(session_row.attempt_count) >= 1

    recomputed = hashlib.sha256(
        json.dumps(c["handshake_payload_json"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert recomputed == c["handshake_sha256"]

    dup = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/handshakes",
        headers=headers,
        json={"session_token": session_token, "idempotency_key": "hs-77-idem"},
    )
    assert dup.status_code == 201
    assert dup.json()["handshake_id"] == c["handshake_id"]

    rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerHandshake.id))).scalar_one())
    assert rows == 1

    listed = client.get(RUNNER_HANDSHAKES, headers=headers)
    assert listed.status_code == 200
    assert any(item["handshake_id"] == c["handshake_id"] for item in listed.json())

    detail = client.get(f"{RUNNER_HANDSHAKES}/{c['handshake_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json().get("session_token") is None

    cross_detail = client.get(f"{RUNNER_HANDSHAKES}/{c['handshake_id']}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    verify_ok = client.post(f"{RUNNER_HANDSHAKES}/{c['handshake_id']}/verify", headers=headers, json={})
    assert verify_ok.status_code == 200
    assert verify_ok.json()["valid"] is True

    bad_dry_run = client.post(
        f"{RUNNER_HANDSHAKES}/{c['handshake_id']}/verify",
        headers=headers,
        json={"handshake_payload_json": {**c["handshake_payload_json"], "dry_run": False}},
    )
    assert bad_dry_run.status_code == 200
    assert bad_dry_run.json()["valid"] is False
    assert "dry_run_must_be_true" in bad_dry_run.json()["validation_errors"]

    bad_exec = client.post(
        f"{RUNNER_HANDSHAKES}/{c['handshake_id']}/verify",
        headers=headers,
        json={"handshake_payload_json": {**c["handshake_payload_json"], "execution_allowed": True}},
    )
    assert bad_exec.status_code == 200
    assert bad_exec.json()["valid"] is False
    assert "execution_allowed_must_be_false" in bad_exec.json()["validation_errors"]


def test_phase77_handshake_create_blocked_guards_and_revoke_archive_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p77-guards")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P77-Guards")

    expired_seed = _create_session(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )
    expired_session_id = expired_seed["session"]["session_id"]
    expired_row = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(expired_session_id))
    expired_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()

    expired_create = client.post(
        f"{RUNNER_SESSIONS}/{expired_session_id}/handshakes",
        headers=headers,
        json={"session_token": expired_seed["session"]["session_token"]},
    )
    assert expired_create.status_code == 400

    revoked_session_seed = _create_session(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )
    revoked_session_id = revoked_session_seed["session"]["session_id"]
    revoked_session_resp = client.post(
        f"{RUNNER_SESSIONS}/{revoked_session_id}/revoke",
        headers=headers,
        json={"revoke_reason": "session revoked"},
    )
    assert revoked_session_resp.status_code == 200

    revoked_session_create = client.post(
        f"{RUNNER_SESSIONS}/{revoked_session_id}/handshakes",
        headers=headers,
        json={"session_token": revoked_session_seed["session"]["session_token"]},
    )
    assert revoked_session_create.status_code == 400

    revoked_admission_seed = _create_session(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )
    revoked_admission_id = revoked_admission_seed["admission"]["admission_id"]
    revoke_adm = client.post(
        f"/api/v1/ai-governance/autopilot/runner-admissions/{revoked_admission_id}/revoke",
        headers=headers,
        json={"revoke_reason": "admission revoked"},
    )
    assert revoke_adm.status_code == 200

    revoked_admission_create = client.post(
        f"{RUNNER_SESSIONS}/{revoked_admission_seed['session']['session_id']}/handshakes",
        headers=headers,
        json={"session_token": revoked_admission_seed["session"]["session_token"]},
    )
    assert revoked_admission_create.status_code == 400

    ok_seed = _create_session(
        client,
        headers,
        assessment_id=assessment["id"],
        ai_system_id=ai["id"],
        db_session=db_session,
        organization_id=org["organization_id"],
    )
    created = client.post(
        f"{RUNNER_SESSIONS}/{ok_seed['session']['session_id']}/handshakes",
        headers=headers,
        json={"session_token": ok_seed["session"]["session_token"]},
    )
    assert created.status_code == 201
    handshake_id = created.json()["handshake_id"]

    missing_reason = client.post(f"{RUNNER_HANDSHAKES}/{handshake_id}/revoke", headers=headers, json={})
    assert missing_reason.status_code == 422

    revoked = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/revoke",
        headers=headers,
        json={"revoke_reason": "manual revoke"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["handshake_status"] == "revoked"

    archived = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/archive",
        headers=headers,
        json={"reason": "archive"},
    )
    assert archived.status_code == 200
    assert archived.json()["handshake_status"] == "archived"

    row = db_session.get(GovernanceAutopilotRunnerHandshake, uuid.UUID(handshake_id))
    assert row is not None

    summary = client.get(f"{RUNNER_HANDSHAKES}/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_handshakes"] >= 1
    assert "ready_for_future_runner_count" in sb
    assert "blocked_count" in sb
    assert "revoked_count" in sb
    assert "archived_count" in sb


def test_phase77_handshake_audit_boundaries_contract_group_and_no_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p77-audit")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P77-Audit")
    seeded = _create_session(
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

    read_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.get(RUNNER_HANDSHAKE_CONTRACT, headers=headers)
    _ = client.post(f"{RUNNER_SESSIONS}/{seeded['session']['session_id']}/handshake-preview", headers=headers, json={})
    _ = client.get(RUNNER_HANDSHAKES, headers=headers)
    _ = client.get(f"{RUNNER_HANDSHAKES}/summary", headers=headers)
    read_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert read_after == read_before

    created = client.post(
        f"{RUNNER_SESSIONS}/{seeded['session']['session_id']}/handshakes",
        headers=headers,
        json={"session_token": seeded["session"]["session_token"]},
    )
    assert created.status_code == 201
    handshake_id = created.json()["handshake_id"]

    _ = client.post(f"{RUNNER_HANDSHAKES}/{handshake_id}/verify", headers=headers, json={})

    _ = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/revoke",
        headers=headers,
        json={"revoke_reason": "reason"},
    )
    _ = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/archive",
        headers=headers,
        json={"reason": "reason"},
    )

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_runner_handshakes" in groups

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
                AuditLog.action.like("governance_autopilot_runner_handshake.%"),
            )
        ).all()
    }
    assert "governance_autopilot_runner_handshake.created" in actions
    assert "governance_autopilot_runner_handshake.revoked" in actions
    assert "governance_autopilot_runner_handshake.archived" in actions

    admission_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerAdmission.id))).scalar_one())
    session_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerSession.id))).scalar_one())
    handshake_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerHandshake.id))).scalar_one())
    assert admission_rows >= 1
    assert session_rows >= 1
    assert handshake_rows >= 1
