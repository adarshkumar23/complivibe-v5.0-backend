import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_runner_admission import GovernanceAutopilotRunnerAdmission
from app.models.governance_autopilot_runner_session import GovernanceAutopilotRunnerSession
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_runner_admissions_phase75 import (
    RUNNER_ADMISSIONS,
    RUNNER_SIMS,
    _create_blocked_simulation,
    _create_ready_simulation,
)
from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed

RUNNER_SESSIONS = "/api/v1/ai-governance/autopilot/runner-sessions"


def _create_admitted_admission(client, headers: dict[str, str], *, assessment_id: str, ai_system_id: str) -> dict:
    sim = _create_ready_simulation(client, headers, assessment_id=assessment_id, ai_system_id=ai_system_id)
    created = client.post(f"{RUNNER_SIMS}/{sim['simulation_id']}/admissions", headers=headers, json={})
    assert created.status_code == 201
    body = created.json()
    assert body["admission_status"] == "admitted"
    assert body.get("handoff_token")
    return body


def test_phase76_runner_session_preview_no_write_no_audit_and_token_validation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p76-preview")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-Preview")
    admission = _create_admitted_admission(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])

    before_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerSession.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    preview_ok = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/session-preview",
        headers=headers,
        json={"handoff_token": admission["handoff_token"]},
    )
    assert preview_ok.status_code == 200
    body = preview_ok.json()
    assert body["would_create_session"] is True
    assert body["proposed_session_status"] == "active"
    assert body["runner_admission_id"] == admission["admission_id"]
    assert body["max_attempts"] == 3
    assert body["replay_window_seconds"] == 600

    preview_bad = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/session-preview",
        headers=headers,
        json={"handoff_token": "wrong-token"},
    )
    assert preview_bad.status_code == 200
    assert preview_bad.json()["would_create_session"] is False
    assert "token_mismatch" in preview_bad.json()["blocked_reasons"]

    after_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerSession.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit


def test_phase76_runner_session_create_detail_and_create_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p76-create")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-Create")
    admission = _create_admitted_admission(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])

    created = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": admission["handoff_token"]},
    )
    assert created.status_code == 201
    c = created.json()
    assert c["session_status"] == "active"
    assert isinstance(c.get("session_token"), str) and c["session_token"]
    assert c.get("session_token_fingerprint")

    row = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(c["session_id"]))
    assert row is not None
    assert row.session_token_hash is not None
    assert row.session_token_hash != c["session_token"]
    assert row.session_token_fingerprint == c["session_token_fingerprint"]
    assert row.admission_token_fingerprint == admission["handoff_token_fingerprint"]

    detail = client.get(f"{RUNNER_SESSIONS}/{c['session_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json().get("session_token") is None

    listed = client.get(RUNNER_SESSIONS, headers=headers)
    assert listed.status_code == 200
    assert any(item["session_id"] == c["session_id"] and item.get("session_token") is None for item in listed.json())

    wrong_token_create = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": "wrong-token"},
    )
    assert wrong_token_create.status_code == 400

    blocked_sim = _create_blocked_simulation(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])
    blocked_admission = client.post(f"{RUNNER_SIMS}/{blocked_sim['simulation_id']}/admissions", headers=headers, json={})
    assert blocked_admission.status_code == 201
    assert blocked_admission.json()["admission_status"] == "blocked"
    blocked_create = client.post(
        f"{RUNNER_ADMISSIONS}/{blocked_admission.json()['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": "anything"},
    )
    assert blocked_create.status_code == 400


def test_phase76_runner_session_verify_attempt_lock_expiry_revoke_archive(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p76-verify-1")
    org2 = bootstrap_org_user(client, email_prefix="p76-verify-2")
    headers = org1["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-Verify")
    admission = _create_admitted_admission(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])

    created = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": admission["handoff_token"], "max_attempts": 2, "replay_window_seconds": 1},
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]
    session_token = created.json()["session_token"]

    cross = client.get(f"{RUNNER_SESSIONS}/{session_id}", headers=org2["org_headers"])
    assert cross.status_code == 404

    verify_ok = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/verify",
        headers=headers,
        json={"session_token": session_token},
    )
    assert verify_ok.status_code == 200
    assert verify_ok.json()["valid"] is True
    assert verify_ok.json()["attempt_count"] == 1

    verify_bad = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/verify",
        headers=headers,
        json={"session_token": "wrong-token"},
    )
    assert verify_bad.status_code == 200
    assert verify_bad.json()["valid"] is False
    assert verify_bad.json()["attempt_count"] == 2
    assert "session_token_mismatch" in verify_bad.json()["validation_errors"]

    locked = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/verify",
        headers=headers,
        json={"session_token": "wrong-token-again"},
    )
    assert locked.status_code == 200
    assert locked.json()["valid"] is False
    assert locked.json()["session_status"] == "locked"
    assert locked.json()["attempt_count"] == 3

    revoke_missing_reason = client.post(f"{RUNNER_SESSIONS}/{session_id}/revoke", headers=headers, json={})
    assert revoke_missing_reason.status_code == 422

    revoked = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/revoke",
        headers=headers,
        json={"revoke_reason": "manual revoke"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["session_status"] == "revoked"

    revoked_verify = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/verify",
        headers=headers,
        json={"session_token": session_token},
    )
    assert revoked_verify.status_code == 200
    assert revoked_verify.json()["valid"] is False
    assert revoked_verify.json()["session_status"] == "revoked"

    archived = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/archive",
        headers=headers,
        json={"reason": "archive"},
    )
    assert archived.status_code == 200
    assert archived.json()["session_status"] == "archived"

    row = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(session_id))
    assert row is not None

    archived_verify = client.post(
        f"{RUNNER_SESSIONS}/{session_id}/verify",
        headers=headers,
        json={"session_token": session_token},
    )
    assert archived_verify.status_code == 200
    assert archived_verify.json()["valid"] is False
    assert archived_verify.json()["session_status"] == "archived"

    exp_created = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": admission["handoff_token"], "expires_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat()},
    )
    assert exp_created.status_code == 201
    exp_id = exp_created.json()["session_id"]
    exp_token = exp_created.json()["session_token"]
    row_exp = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(exp_id))
    row_exp.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()

    expired_verify = client.post(
        f"{RUNNER_SESSIONS}/{exp_id}/verify",
        headers=headers,
        json={"session_token": exp_token},
    )
    assert expired_verify.status_code == 200
    assert expired_verify.json()["valid"] is False
    assert expired_verify.json()["expired"] is True
    assert "session_expired" in expired_verify.json()["validation_errors"]


def test_phase76_runner_sessions_expire_summary_contract_and_audit_boundaries(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p76-summary")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-Summary")
    admission = _create_admitted_admission(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])

    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    created = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": admission["handoff_token"], "max_attempts": 2},
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]
    token = created.json()["session_token"]

    read_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/session-preview",
        headers=headers,
        json={"handoff_token": admission["handoff_token"]},
    )
    _ = client.get(RUNNER_SESSIONS, headers=headers)
    _ = client.get(f"{RUNNER_SESSIONS}/{session_id}", headers=headers)
    _ = client.get(f"{RUNNER_SESSIONS}/summary", headers=headers)
    read_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert read_after == read_before

    _ = client.post(f"{RUNNER_SESSIONS}/{session_id}/verify", headers=headers, json={"session_token": token})
    _ = client.post(f"{RUNNER_SESSIONS}/{session_id}/verify", headers=headers, json={"session_token": "wrong-token"})
    _ = client.post(f"{RUNNER_SESSIONS}/{session_id}/verify", headers=headers, json={"session_token": "wrong-token-again"})
    _ = client.post(f"{RUNNER_SESSIONS}/{session_id}/revoke", headers=headers, json={"revoke_reason": "reason"})
    _ = client.post(f"{RUNNER_SESSIONS}/{session_id}/archive", headers=headers, json={"reason": "reason"})

    stale = client.post(
        f"{RUNNER_ADMISSIONS}/{admission['admission_id']}/sessions",
        headers=headers,
        json={"handoff_token": admission["handoff_token"]},
    )
    assert stale.status_code == 201
    stale_id = stale.json()["session_id"]
    stale_row = db_session.get(GovernanceAutopilotRunnerSession, uuid.UUID(stale_id))
    stale_row.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.flush()
    expire = client.post(f"{RUNNER_SESSIONS}/expire-stale", headers=headers, json={})
    assert expire.status_code == 200
    assert expire.json()["expired_count"] >= 1
    assert stale_id in expire.json()["expired_session_ids"]

    summary = client.get(f"{RUNNER_SESSIONS}/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_sessions"] >= 2
    assert "active_count" in sb
    assert "expired_count" in sb
    assert "locked_count" in sb
    assert "revoked_count" in sb

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_runner_sessions" in groups

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
                AuditLog.action.like("governance_autopilot_runner_session.%"),
            )
        ).all()
    }
    assert "governance_autopilot_runner_session.created" in actions
    assert "governance_autopilot_runner_session.verified" in actions
    assert "governance_autopilot_runner_session.verification_failed" in actions
    assert "governance_autopilot_runner_session.locked" in actions
    assert "governance_autopilot_runner_session.revoked" in actions
    assert "governance_autopilot_runner_session.archived" in actions
    assert "governance_autopilot_runner_session.expired" in actions

    admission_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerAdmission.id))).scalar_one())
    session_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerSession.id))).scalar_one())
    assert admission_rows >= 1
    assert session_rows >= 2
