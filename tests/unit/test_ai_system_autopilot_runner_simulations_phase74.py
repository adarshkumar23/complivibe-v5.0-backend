import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_runner_simulation import GovernanceAutopilotRunnerSimulation
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_execution_approvals_phase72 import _candidate
from tests.unit.test_ai_system_autopilot_policies_phase70 import POLICY_BASE, _seed

INTENTS_BASE = "/api/v1/ai-governance/autopilot/execution-intents"
APPROVALS_BASE = "/api/v1/ai-governance/autopilot/execution-approvals"
RUNNER_CONTRACT = "/api/v1/ai-governance/autopilot/runner-interface/contract"
RUNNER_VERIFY = "/api/v1/ai-governance/autopilot/runner-interface/verify-handoff"
RUNNER_SIMS = "/api/v1/ai-governance/autopilot/runner-simulations"


def _create_require_approval_policy(client, headers: dict[str, str]) -> str:
    resp = client.post(
        POLICY_BASE,
        headers=headers,
        json={"name": "p74-policy", "mode": "require_approval", "status": "active", "is_default": True},
    )
    assert resp.status_code == 201
    return resp.json()["policy_id"]


def _create_intent(client, headers: dict[str, str], payload: dict) -> dict:
    resp = client.post(INTENTS_BASE, headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_phase74_runner_interface_contract_and_preview_read_only(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p74-contract")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P74-Preview")
    policy_id = _create_require_approval_policy(client, headers)

    intent = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                action_type="refresh_signals",
                priority_band="high",
            ),
            "policy_id": policy_id,
        },
    )

    before_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerSimulation.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    contract = client.get(RUNNER_CONTRACT, headers=headers)
    assert contract.status_code == 200
    c = contract.json()
    assert c["handoff_schema_version"]
    assert c["dry_run_only"] is True
    assert c["execution_allowed"] is False

    preview = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/runner-handoff/preview",
        headers=headers,
        json={},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["execution_intent_id"] == intent["intent_id"]
    assert body["dry_run"] is True
    assert body["execution_allowed"] is False
    assert isinstance(body["idempotency_key"], str) and len(body["idempotency_key"]) == 64
    assert body["handoff_payload_json"]["dry_run"] is True
    assert body["handoff_payload_json"]["execution_allowed"] is False

    verify_ok = client.post(RUNNER_VERIFY, headers=headers, json={"handoff_payload_json": body["handoff_payload_json"]})
    assert verify_ok.status_code == 200
    assert verify_ok.json()["valid"] is True

    verify_bad = client.post(
        RUNNER_VERIFY,
        headers=headers,
        json={
            "handoff_payload_json": {
                **body["handoff_payload_json"],
                "execution_allowed": True,
                "dry_run": False,
            }
        },
    )
    assert verify_bad.status_code == 200
    assert verify_bad.json()["valid"] is False
    assert "execution_allowed_must_be_false" in verify_bad.json()["validation_errors"]
    assert "dry_run_must_be_true" in verify_bad.json()["validation_errors"]

    after_rows = int(db_session.execute(select(func.count(GovernanceAutopilotRunnerSimulation.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit


def test_phase74_create_runner_simulation_idempotency_and_archive(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p74-create")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P74-Create")
    policy_id = _create_require_approval_policy(client, headers)

    intent = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                action_type="refresh_signals",
                priority_band="high",
            ),
            "policy_id": policy_id,
        },
    )
    request_approval = client.post(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requests", headers=headers, json={})
    assert request_approval.status_code == 201
    approval_id = request_approval.json()["approval_id"]
    approve = client.post(
        f"{APPROVALS_BASE}/{approval_id}/approve",
        headers=headers,
        json={"decision_reason": "approve for ready state"},
    )
    assert approve.status_code == 200

    before_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotRunnerSimulation.id)).where(
                GovernanceAutopilotRunnerSimulation.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )

    created = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/runner-simulations",
        headers=headers,
        json={"approval_id": approval_id, "idempotency_key": "fixed-idempotency-key"},
    )
    assert created.status_code == 201
    c1 = created.json()
    assert c1["simulation_status"] == "ready_for_runner"
    assert isinstance(c1["simulation_sha256"], str) and len(c1["simulation_sha256"]) == 64

    created_again = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/runner-simulations",
        headers=headers,
        json={"approval_id": approval_id, "idempotency_key": "fixed-idempotency-key"},
    )
    assert created_again.status_code == 201
    c2 = created_again.json()
    assert c2["simulation_id"] == c1["simulation_id"]

    after_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotRunnerSimulation.id)).where(
                GovernanceAutopilotRunnerSimulation.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    assert after_rows == before_rows + 1

    listed = client.get(RUNNER_SIMS, headers=headers)
    assert listed.status_code == 200
    assert any(r["simulation_id"] == c1["simulation_id"] for r in listed.json())

    detail = client.get(f"{RUNNER_SIMS}/{c1['simulation_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["simulation_id"] == c1["simulation_id"]

    archive = client.post(f"{RUNNER_SIMS}/{c1['simulation_id']}/archive", headers=headers, json={"reason": "archive test"})
    assert archive.status_code == 200
    assert archive.json()["simulation_status"] == "archived"


def test_phase74_runner_simulation_statuses_summary_tenant_scope_and_contract(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p74-status-1")
    org2 = bootstrap_org_user(client, email_prefix="p74-status-2")
    headers = org1["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P74-Status")
    policy_id = _create_require_approval_policy(client, headers)

    # approval_required
    intent_approval_required = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                action_type="refresh_signals",
                priority_band="high",
            ),
            "policy_id": policy_id,
        },
    )
    sim_required = client.post(
        f"{INTENTS_BASE}/{intent_approval_required['intent_id']}/runner-simulations",
        headers=headers,
        json={},
    )
    assert sim_required.status_code == 201
    assert sim_required.json()["simulation_status"] == "approval_required"

    # blocked/capability denied
    intent_blocked = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                action_type="create_task",
                priority_band="urgent",
            ),
            "policy_id": policy_id,
        },
    )
    sim_blocked = client.post(
        f"{INTENTS_BASE}/{intent_blocked['intent_id']}/runner-simulations",
        headers=headers,
        json={},
    )
    assert sim_blocked.status_code == 201
    assert sim_blocked.json()["simulation_status"] in {"blocked", "policy_denied", "capability_denied"}

    summary = client.get(f"{RUNNER_SIMS}/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_simulations"] >= 2
    assert isinstance(sb["by_status"], dict)

    cross_tenant = client.get(f"{RUNNER_SIMS}/{sim_required.json()['simulation_id']}", headers=org2["org_headers"])
    assert cross_tenant.status_code == 404

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_runner_interface" in groups
    assert "governance_autopilot_runner_simulations" in groups


def test_phase74_runner_simulation_endpoints_no_execution_or_source_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p74-safety")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P74-Safety")

    intent = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                action_type="refresh_signals",
                priority_band="low",
            ),
        },
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

    sim = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/runner-simulations",
        headers=headers,
        json={},
    )
    assert sim.status_code == 201

    read_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.get(RUNNER_CONTRACT, headers=headers)
    _ = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/runner-handoff/preview",
        headers=headers,
        json={},
    )
    _ = client.get(RUNNER_SIMS, headers=headers)
    _ = client.get(f"{RUNNER_SIMS}/{sim.json()['simulation_id']}", headers=headers)
    _ = client.get(f"{RUNNER_SIMS}/summary", headers=headers)
    _ = client.post(RUNNER_VERIFY, headers=headers, json={"handoff_payload_json": sim.json()["handoff_payload_json"]})
    read_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert read_after == read_before

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
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews
    assert after_audit > before_audit

    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action.like("governance_autopilot_runner_simulation.%"),
            )
        ).all()
    }
    assert "governance_autopilot_runner_simulation.created" in actions
