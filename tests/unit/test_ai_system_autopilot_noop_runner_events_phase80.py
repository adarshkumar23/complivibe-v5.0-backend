import hashlib
import json
import uuid
from pathlib import Path
import re

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_noop_runner_event import GovernanceAutopilotNoopRunnerEvent
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed
from tests.unit.test_ai_system_autopilot_runner_handshakes_phase77 import _create_session

PHASE8_CONTRACT = "/api/v1/ai-governance/contracts/phase8"
NOOP_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/contract"
RUNNER_HANDSHAKES = "/api/v1/ai-governance/autopilot/runner-handshakes"
NOOP_EVENTS = "/api/v1/ai-governance/autopilot/noop-runner/events"


def _phase8_router_paths_in_order() -> list[str]:
    source = Path("app/api/v1/ai_governance.py").read_text(encoding="utf-8")
    start = source.index('@router.get("/contracts/phase8"')
    end = source.index("def _policy_read(")
    segment = source[start:end]
    seg_lines = segment.splitlines()
    paths: list[str] = []
    i = 0
    while i < len(seg_lines):
        line = seg_lines[i]
        if "@router." not in line:
            i += 1
            continue
        blob = line
        j = i + 1
        while j < len(seg_lines) and ")" not in blob and (j - i) < 12:
            blob += "\n" + seg_lines[j]
            j += 1
        match = re.search(r'"([^"]+)"', blob)
        if match:
            paths.append(match.group(1))
        i = j
    return paths


def _create_handshake(client, headers: dict[str, str], *, assessment_id: str, ai_system_id: str) -> dict:
    seeded = _create_session(client, headers, assessment_id=assessment_id, ai_system_id=ai_system_id)
    created = client.post(
        f"/api/v1/ai-governance/autopilot/runner-sessions/{seeded['session']['session_id']}/handshakes",
        headers=headers,
        json={"session_token": seeded["session"]["session_token"]},
    )
    assert created.status_code == 201
    return {
        "seeded": seeded,
        "handshake": created.json(),
    }


def test_phase80_noop_runner_route_ordering_static_before_dynamic():
    paths = _phase8_router_paths_in_order()
    assert "/contracts/phase8" in paths
    assert "/autopilot/noop-runner/contract" in paths
    assert "/autopilot/noop-runner/events/summary" in paths
    assert "/autopilot/noop-runner/events/{event_id}" in paths
    assert paths.index("/autopilot/noop-runner/events/summary") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/contract") < paths.index("/autopilot/noop-runner/events/{event_id}")


def test_phase80_noop_runner_contract_and_preview_are_read_only(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p80-contract")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P80-Contract")
    seeded = _create_handshake(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])

    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    p8 = phase8.json()
    assert p8["phase"] == "phase8"
    assert p8["execution_allowed"] is False
    assert p8["real_runner_present"] is False
    assert p8["job_queue_present"] is False
    assert p8["noop_runner_only"] is True
    groups = {group["group_key"] for group in p8["groups"]}
    assert "governance_noop_runner_events" in groups

    contract = client.get(NOOP_CONTRACT, headers=headers)
    assert contract.status_code == 200
    cb = contract.json()
    assert cb["noop_only"] is True
    assert cb["dry_run"] is True
    assert cb["execution_allowed"] is False
    assert "noop_runner_control_plane_check" in cb["supported_event_types"]

    before_rows = int(db_session.execute(select(func.count(GovernanceAutopilotNoopRunnerEvent.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    preview = client.post(
        f"{RUNNER_HANDSHAKES}/{seeded['handshake']['handshake_id']}/noop-runner/preview",
        headers=headers,
        json={},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["would_log_event"] is True
    assert body["proposed_event_status"] == "logged"
    assert body["event_payload_json"]["noop_only"] is True
    assert body["event_payload_json"]["dry_run"] is True
    assert body["event_payload_json"]["execution_allowed"] is False
    assert body["noop_result_json"]["action_executed"] is False
    assert body["noop_result_json"]["jobs_queued"] is False
    assert body["noop_result_json"]["tasks_created"] is False
    assert body["noop_result_json"]["reviews_created"] is False

    after_rows = int(db_session.execute(select(func.count(GovernanceAutopilotNoopRunnerEvent.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit


def test_phase80_noop_runner_event_create_idempotency_verify_and_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p80-create-1")
    org2 = bootstrap_org_user(client, email_prefix="p80-create-2")
    headers = org1["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P80-Create")
    seeded = _create_handshake(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])
    handshake_id = seeded["handshake"]["handshake_id"]

    created = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p80-idem"},
    )
    assert created.status_code == 201
    c = created.json()
    assert c["event_status"] == "logged"
    assert c["event_type"] == "noop_runner_control_plane_check"
    assert c["noop_only"] is True
    assert c["dry_run"] is True
    assert c["execution_allowed"] is False
    assert c["idempotency_key"] == "p80-idem"
    assert c.get("session_token") is None
    assert c.get("handoff_token") is None

    recomputed = hashlib.sha256(
        json.dumps(c["event_payload_json"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert recomputed == c["event_sha256"]

    dup = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p80-idem"},
    )
    assert dup.status_code == 201
    assert dup.json()["event_id"] == c["event_id"]
    rows = int(db_session.execute(select(func.count(GovernanceAutopilotNoopRunnerEvent.id))).scalar_one())
    assert rows == 1

    listed = client.get(NOOP_EVENTS, headers=headers)
    assert listed.status_code == 200
    assert any(item["event_id"] == c["event_id"] for item in listed.json())
    detail = client.get(f"{NOOP_EVENTS}/{c['event_id']}", headers=headers)
    assert detail.status_code == 200

    cross_detail = client.get(f"{NOOP_EVENTS}/{c['event_id']}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    verify_ok = client.post(f"{NOOP_EVENTS}/{c['event_id']}/verify", headers=headers, json={})
    assert verify_ok.status_code == 200
    assert verify_ok.json()["valid"] is True

    verify_bad_noop = client.post(
        f"{NOOP_EVENTS}/{c['event_id']}/verify",
        headers=headers,
        json={"event_payload_json": {**c["event_payload_json"], "noop_only": False}},
    )
    assert verify_bad_noop.status_code == 200
    assert verify_bad_noop.json()["valid"] is False
    assert "noop_only_must_be_true" in verify_bad_noop.json()["validation_errors"]

    verify_bad_dry = client.post(
        f"{NOOP_EVENTS}/{c['event_id']}/verify",
        headers=headers,
        json={"event_payload_json": {**c["event_payload_json"], "dry_run": False}},
    )
    assert verify_bad_dry.status_code == 200
    assert verify_bad_dry.json()["valid"] is False
    assert "dry_run_must_be_true" in verify_bad_dry.json()["validation_errors"]

    verify_bad_exec = client.post(
        f"{NOOP_EVENTS}/{c['event_id']}/verify",
        headers=headers,
        json={"event_payload_json": {**c["event_payload_json"], "execution_allowed": True}},
    )
    assert verify_bad_exec.status_code == 200
    assert verify_bad_exec.json()["valid"] is False
    assert "execution_allowed_must_be_false" in verify_bad_exec.json()["validation_errors"]


def test_phase80_noop_runner_event_blocked_archive_summary_and_audit_boundaries(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p80-boundary")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P80-Boundary")
    seeded = _create_handshake(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])
    handshake_id = seeded["handshake"]["handshake_id"]

    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    # First create a logged event.
    created = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p80-log"},
    )
    assert created.status_code == 201
    event_id = created.json()["event_id"]

    # Read-only endpoints must not audit.
    read_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.get(PHASE8_CONTRACT, headers=headers)
    _ = client.get(NOOP_CONTRACT, headers=headers)
    _ = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/noop-runner/preview",
        headers=headers,
        json={},
    )
    _ = client.get(NOOP_EVENTS, headers=headers)
    _ = client.get(f"{NOOP_EVENTS}/{event_id}", headers=headers)
    _ = client.get(f"{NOOP_EVENTS}/summary", headers=headers)
    _ = client.post(f"{NOOP_EVENTS}/{event_id}/verify", headers=headers, json={})
    read_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert read_after == read_before

    # Revoke handshake then create blocked no-op event.
    revoke_handshake = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/revoke",
        headers=headers,
        json={"revoke_reason": "manual revoke"},
    )
    assert revoke_handshake.status_code == 200
    blocked = client.post(
        f"{RUNNER_HANDSHAKES}/{handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p80-blocked"},
    )
    assert blocked.status_code == 201
    assert blocked.json()["event_status"] == "blocked"

    archived = client.post(
        f"{NOOP_EVENTS}/{event_id}/archive",
        headers=headers,
        json={"reason": "archive"},
    )
    assert archived.status_code == 200
    assert archived.json()["event_status"] == "archived"

    row = db_session.get(GovernanceAutopilotNoopRunnerEvent, uuid.UUID(event_id))
    assert row is not None

    summary = client.get(f"{NOOP_EVENTS}/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_events"] >= 2
    assert "logged_count" in sb
    assert "blocked_count" in sb
    assert "archived_count" in sb

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
                AuditLog.action.like("governance_autopilot_noop_runner_event.%"),
            )
        ).all()
    }
    assert "governance_autopilot_noop_runner_event.created" in actions
    assert "governance_autopilot_noop_runner_event.archived" in actions
