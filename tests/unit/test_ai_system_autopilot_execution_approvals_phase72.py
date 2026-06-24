import uuid

from sqlalchemy import func, select

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_execution_approval import GovernanceAutopilotExecutionApproval
from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_policies_phase70 import (
    POLICY_BASE,
    _create_recommendation_snapshot,
    _create_draft_snapshot,
    _seed,
)

INTENTS_BASE = "/api/v1/ai-governance/autopilot/execution-intents"
APPROVALS_BASE = "/api/v1/ai-governance/autopilot/execution-approvals"


def _candidate(*, assessment_id: str, ai_system_id: str, action_type: str, priority_band: str = "high") -> dict:
    return {
        "action_key": f"{action_type}_{assessment_id}",
        "title": "Autopilot candidate",
        "description": "Deterministic test candidate",
        "action_type": action_type,
        "priority_score": 88,
        "priority_band": priority_band,
        "source_signal_ids": [],
        "source_reason_codes": ["classification_needs_review"],
        "target_entity_type": "risk_assessment",
        "target_entity_id": assessment_id,
        "related_ai_system_id": ai_system_id,
        "related_risk_assessment_id": assessment_id,
        "rationale": "test",
        "rationale_json": {},
        "human_approval_required": True,
        "automation_allowed": False,
        "target_route_hint": None,
    }


def _create_require_approval_policy(client, headers: dict[str, str]) -> str:
    resp = client.post(
        POLICY_BASE,
        headers=headers,
        json={"name": "p72-policy", "mode": "require_approval", "status": "active", "is_default": True},
    )
    assert resp.status_code == 201
    return resp.json()["policy_id"]


def _create_intent(client, headers: dict[str, str], payload: dict) -> dict:
    resp = client.post(INTENTS_BASE, headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_phase72_approval_requirements_request_and_readiness_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p72-req")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P72-Req")
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
    assert intent["intent_status"] == "approval_required"

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    reqs = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requirements", headers=headers)
    assert reqs.status_code == 200
    body = reqs.json()
    assert body["intent_id"] == intent["intent_id"]
    assert body["approval_required"] is True
    assert body["blocked"] is False
    assert body["ready_for_runner"] is False
    assert body["readiness_state"] == "approval_required"
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_audit == before_audit

    request_approval = client.post(
        f"{INTENTS_BASE}/{intent['intent_id']}/approval-requests",
        headers=headers,
        json={"approval_note": "Please approve"},
    )
    assert request_approval.status_code == 201
    approval = request_approval.json()
    assert approval["approval_status"] == "requested"
    assert approval["execution_intent_id"] == intent["intent_id"]
    assert approval["approval_policy_snapshot_json"]["policy_id"] == policy_id

    readiness_before = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    assert readiness_before.status_code == 200
    assert readiness_before.json()["ready_for_runner"] is False

    approve = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/approve",
        headers=headers,
        json={"decision_reason": "manual authorize"},
    )
    assert approve.status_code == 200
    assert approve.json()["approval_status"] == "approved"

    readiness_after = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    assert readiness_after.status_code == 200
    rb = readiness_after.json()
    assert rb["latest_approval_id"] == approval["approval_id"]
    assert rb["latest_approval_status"] == "approved"
    assert rb["ready_for_runner"] is True
    assert rb["readiness_state"] == "ready_for_runner"

    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action.like("governance_autopilot_execution_approval.%"),
            )
        ).all()
    }
    assert "governance_autopilot_execution_approval.requested" in actions
    assert "governance_autopilot_execution_approval.approved" in actions


def test_phase72_request_approval_blocked_for_archived_or_blocked_intent(client):
    org = bootstrap_org_user(client, email_prefix="p72-block")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P72-Block")

    blocked_intent = _create_intent(
        client,
        headers,
        {
            "source_type": "candidate_action",
            "candidate_action_json": _candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                action_type="create_task",
            ),
        },
    )
    assert blocked_intent["intent_status"] == "blocked"

    req_blocked = client.post(
        f"{INTENTS_BASE}/{blocked_intent['intent_id']}/approval-requests",
        headers=headers,
        json={"approval_note": "should fail"},
    )
    assert req_blocked.status_code == 400

    archived_intent = _create_intent(
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
    archive = client.post(
        f"{INTENTS_BASE}/{archived_intent['intent_id']}/archive",
        headers=headers,
        json={"reason": "archive"},
    )
    assert archive.status_code == 200

    req_archived = client.post(
        f"{INTENTS_BASE}/{archived_intent['intent_id']}/approval-requests",
        headers=headers,
        json={"approval_note": "should fail"},
    )
    assert req_archived.status_code == 400


def test_phase72_reject_cancel_lists_summary_contract_and_no_source_mutation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p72-list-1")
    org2 = bootstrap_org_user(client, email_prefix="p72-list-2")
    headers = org1["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P72-List")
    _create_recommendation_snapshot(client, headers, assessment_id=assessment["id"])
    _create_draft_snapshot(client, headers, assessment_id=assessment["id"])
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

    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org1["organization_id"]))
        ).scalars()
    }
    before_assessment = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    before_assessment_risk = before_assessment.risk_level
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    req = client.post(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requests", headers=headers, json={})
    assert req.status_code == 201
    approval_id = req.json()["approval_id"]

    reject_missing_reason = client.post(
        f"{APPROVALS_BASE}/{approval_id}/reject",
        headers=headers,
        json={},
    )
    assert reject_missing_reason.status_code == 422

    reject = client.post(
        f"{APPROVALS_BASE}/{approval_id}/reject",
        headers=headers,
        json={"decision_reason": "not acceptable"},
    )
    assert reject.status_code == 200
    assert reject.json()["approval_status"] == "rejected"

    req2 = client.post(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requests", headers=headers, json={"approval_note": "again"})
    assert req2.status_code == 201
    approval2_id = req2.json()["approval_id"]

    cancel = client.post(
        f"{APPROVALS_BASE}/{approval2_id}/cancel",
        headers=headers,
        json={"decision_reason": "operator cancelled"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["approval_status"] == "cancelled"

    list_for_intent = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requests", headers=headers)
    assert list_for_intent.status_code == 200
    assert len(list_for_intent.json()) >= 2

    list_all = client.get(f"{APPROVALS_BASE}?approval_status=cancelled", headers=headers)
    assert list_all.status_code == 200
    assert all(row["approval_status"] == "cancelled" for row in list_all.json())

    detail = client.get(f"{APPROVALS_BASE}/{approval_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["approval_id"] == approval_id

    cross_tenant = client.get(f"{APPROVALS_BASE}/{approval_id}", headers=org2["org_headers"])
    assert cross_tenant.status_code == 404

    blocked_readiness = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    assert blocked_readiness.status_code == 200

    summary = client.get(f"{APPROVALS_BASE}/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_approvals"] >= 2
    assert "requested" in sb["by_status"] or "rejected" in sb["by_status"]

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_execution_approvals" in groups

    after_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org1["organization_id"]))
        ).scalars()
    }
    after_assessment = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    assert before_signals == after_signals
    assert before_assessment_risk == after_assessment.risk_level
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews

    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org1["organization_id"]),
                AuditLog.action.like("governance_autopilot_execution_approval.%"),
            )
        ).all()
    }
    assert "governance_autopilot_execution_approval.requested" in actions
    assert "governance_autopilot_execution_approval.rejected" in actions
    assert "governance_autopilot_execution_approval.cancelled" in actions
    assert after_audit > before_audit

    # no hard delete
    approval_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecutionApproval.id)).where(
                GovernanceAutopilotExecutionApproval.organization_id == uuid.UUID(org1["organization_id"])
            )
        ).scalar_one()
    )
    intent_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecutionIntent.id)).where(
                GovernanceAutopilotExecutionIntent.organization_id == uuid.UUID(org1["organization_id"])
            )
        ).scalar_one()
    )
    assert approval_rows >= 2
    assert intent_rows >= 1


def test_phase72_read_only_approval_endpoints_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p72-readonly")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P72-RO")
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

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/approval-requirements", headers=headers)
    _ = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    _ = client.get(f"{APPROVALS_BASE}/summary", headers=headers)
    _ = client.get(APPROVALS_BASE, headers=headers)
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_audit == before_audit
