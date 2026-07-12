import uuid

from sqlalchemy import func, select

from app.core.security import get_password_hash
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_execution_approval import GovernanceAutopilotExecutionApproval
from app.models.governance_autopilot_execution_approval_vote import GovernanceAutopilotExecutionApprovalVote
from app.models.governance_signal import GovernanceSignal
from app.models.membership import Membership
from app.models.role import Role
from app.models.task import Task
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers
from tests.unit.test_ai_system_autopilot_policies_phase70 import POLICY_BASE, _seed

APPROVAL_POLICY_BASE = "/api/v1/ai-governance/autopilot/approval-policies"
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


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _create_require_approval_policy(client, headers: dict[str, str]) -> str:
    resp = client.post(
        POLICY_BASE,
        headers=headers,
        json={"name": "p73-policy", "mode": "require_approval", "status": "active", "is_default": True},
    )
    assert resp.status_code == 201
    return resp.json()["policy_id"]


def _create_execution_intent(client, headers: dict[str, str], payload: dict) -> dict:
    resp = client.post(INTENTS_BASE, headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def _request_approval(client, headers: dict[str, str], intent_id: str) -> dict:
    resp = client.post(f"{INTENTS_BASE}/{intent_id}/approval-requests", headers=headers, json={})
    assert resp.status_code == 201
    return resp.json()


def test_phase73_approval_policy_crud_resolved_summary_and_validation(client):
    org = bootstrap_org_user(client, email_prefix="p73-pol")
    headers = org["org_headers"]

    invalid_min = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={"name": "bad", "minimum_approvals": 0},
    )
    assert invalid_min.status_code == 422

    created = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={
            "name": "dual-control",
            "status": "active",
            "is_default": True,
            "minimum_approvals": 2,
            "rejection_threshold": 1,
            "require_distinct_approvers": True,
            "block_requester_self_approval": True,
        },
    )
    assert created.status_code == 201
    pid1 = created.json()["approval_policy_id"]
    assert created.json()["minimum_approvals"] == 2

    created2 = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={"name": "single-approver", "status": "active", "is_default": False},
    )
    assert created2.status_code == 201
    pid2 = created2.json()["approval_policy_id"]

    set_default = client.post(f"{APPROVAL_POLICY_BASE}/{pid2}/set-default", headers=headers)
    assert set_default.status_code == 200
    assert set_default.json()["approval_policy_id"] == pid2
    assert set_default.json()["is_default"] is True

    list_resp = client.get(APPROVAL_POLICY_BASE, headers=headers)
    assert list_resp.status_code == 200
    by_id = {row["approval_policy_id"]: row for row in list_resp.json()}
    assert by_id[pid1]["is_default"] is False
    assert by_id[pid2]["is_default"] is True

    resolved = client.get(f"{APPROVAL_POLICY_BASE}/resolved", headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["approval_policy_id"] == pid2
    assert resolved.json()["resolved_source"] == "persisted_default"

    archived = client.post(f"{APPROVAL_POLICY_BASE}/{pid2}/archive", headers=headers, json={"reason": "retired"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    fallback = client.get(f"{APPROVAL_POLICY_BASE}/resolved", headers=headers)
    assert fallback.status_code == 200
    assert fallback.json()["approval_policy_id"] is None
    assert fallback.json()["resolved_source"] == "safe_fallback_default"
    assert fallback.json()["minimum_approvals"] == 1

    summary = client.get(f"{APPROVAL_POLICY_BASE}/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total_policies"] >= 2
    assert "resolved_minimum_approvals" in summary.json()


def test_phase73_vote_quorum_distinct_and_self_approval_block(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p73-vote-owner")
    headers = owner["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P73-Vote")
    policy_id = _create_require_approval_policy(client, headers)
    _ = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={
            "name": "strict-quorum",
            "is_default": True,
            "minimum_approvals": 2,
            "rejection_threshold": 1,
            "require_distinct_approvers": True,
            "block_requester_self_approval": True,
            "require_quorum_for_source_types_json": ["candidate_action"],
        },
    )

    intent = _create_execution_intent(
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
    approval = _request_approval(client, headers, intent["intent_id"])

    self_vote = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/votes/approve",
        headers=headers,
        json={"vote_note": "self"},
    )
    assert self_vote.status_code == 400

    approver2 = _create_active_user_with_role(
        db_session,
        owner["organization_id"],
        "p73-approver2@example.com",
        "admin",
    )
    token2 = login_user(client, approver2.email)
    headers2 = org_headers(token2, owner["organization_id"])

    vote2 = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/votes/approve",
        headers=headers2,
        json={"vote_reason": "approve-1"},
    )
    assert vote2.status_code == 200
    assert vote2.json()["approval_status"] == "requested"
    assert vote2.json()["quorum_met"] is False

    duplicate_vote = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/votes/approve",
        headers=headers2,
        json={"vote_reason": "duplicate"},
    )
    assert duplicate_vote.status_code == 400

    readiness_before = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    assert readiness_before.status_code == 200
    assert readiness_before.json()["ready_for_runner"] is False
    assert readiness_before.json()["quorum_met"] is False

    approver3 = _create_active_user_with_role(
        db_session,
        owner["organization_id"],
        "p73-approver3@example.com",
        "admin",
    )
    token3 = login_user(client, approver3.email)
    headers3 = org_headers(token3, owner["organization_id"])

    vote3 = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/votes/approve",
        headers=headers3,
        json={"vote_reason": "approve-2"},
    )
    assert vote3.status_code == 200
    assert vote3.json()["approval_status"] == "approved"
    assert vote3.json()["quorum_met"] is True

    quorum = client.get(f"{APPROVALS_BASE}/{approval['approval_id']}/quorum-status", headers=headers)
    assert quorum.status_code == 200
    qb = quorum.json()
    assert qb["minimum_approvals"] == 2
    assert qb["approval_vote_count"] == 2
    assert qb["quorum_met"] is True
    assert qb["ready_for_runner"] is True

    readiness_after = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    assert readiness_after.status_code == 200
    assert readiness_after.json()["ready_for_runner"] is True
    assert readiness_after.json()["quorum_met"] is True

    votes = client.get(f"{APPROVALS_BASE}/{approval['approval_id']}/votes", headers=headers)
    assert votes.status_code == 200
    assert len(votes.json()) == 2


def test_phase73_rejection_threshold_and_compatibility_old_endpoints(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p73-compat")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P73-Compat")
    policy_id = _create_require_approval_policy(client, headers)

    create_approval_policy = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={
            "name": "threshold-policy",
            "is_default": True,
            "minimum_approvals": 2,
            "rejection_threshold": 1,
            "require_distinct_approvers": True,
            "block_requester_self_approval": True,
            "require_quorum_for_source_types_json": ["candidate_action"],
        },
    )
    assert create_approval_policy.status_code == 201

    intent = _create_execution_intent(
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
    approval = _request_approval(client, headers, intent["intent_id"])

    reject_missing_reason = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/votes/reject",
        headers=headers,
        json={},
    )
    assert reject_missing_reason.status_code == 422

    approver2 = _create_active_user_with_role(
        db_session,
        org["organization_id"],
        "p73-rejector@example.com",
        "admin",
    )
    token2 = login_user(client, approver2.email)
    headers2 = org_headers(token2, org["organization_id"])

    reject_vote = client.post(
        f"{APPROVALS_BASE}/{approval['approval_id']}/votes/reject",
        headers=headers2,
        json={"vote_reason": "reject-threshold"},
    )
    assert reject_vote.status_code == 200
    assert reject_vote.json()["approval_status"] == "rejected"

    readiness = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)
    assert readiness.status_code == 200
    assert readiness.json()["readiness_state"] == "rejected"
    assert readiness.json()["ready_for_runner"] is False

    # Compatibility: old approve endpoint still works when min approvals = 1.
    policy_single = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={
            "name": "single-approval-policy",
            "is_default": True,
            "minimum_approvals": 1,
            "rejection_threshold": 1,
            "block_requester_self_approval": True,
        },
    )
    assert policy_single.status_code == 201

    intent2 = _create_execution_intent(
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
    approval2 = _request_approval(client, headers, intent2["intent_id"])

    self_approve = client.post(
        f"{APPROVALS_BASE}/{approval2['approval_id']}/approve",
        headers=headers,
        json={"decision_reason": "requester self-approval attempt"},
    )
    assert self_approve.status_code == 400

    old_approve = client.post(
        f"{APPROVALS_BASE}/{approval2['approval_id']}/approve",
        headers=headers2,
        json={"decision_reason": "legacy approve endpoint"},
    )
    assert old_approve.status_code == 200
    assert old_approve.json()["approval_status"] == "approved"

    intent3 = _create_execution_intent(
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
    approval3 = _request_approval(client, headers, intent3["intent_id"])
    old_reject = client.post(
        f"{APPROVALS_BASE}/{approval3['approval_id']}/reject",
        headers=headers2,
        json={"decision_reason": "legacy reject endpoint"},
    )
    assert old_reject.status_code == 200
    assert old_reject.json()["approval_status"] == "rejected"


def test_phase73_read_only_no_audit_and_no_source_mutation_contracts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p73-readonly")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P73-ReadOnly")
    policy_id = _create_require_approval_policy(client, headers)
    _ = client.post(
        APPROVAL_POLICY_BASE,
        headers=headers,
        json={"name": "readonly-policy", "is_default": True, "minimum_approvals": 1},
    )
    intent = _create_execution_intent(
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
    approval = _request_approval(client, headers, intent["intent_id"])

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }

    _ = client.get(f"{APPROVAL_POLICY_BASE}", headers=headers)
    _ = client.get(f"{APPROVAL_POLICY_BASE}/resolved", headers=headers)
    _ = client.get(f"{APPROVAL_POLICY_BASE}/summary", headers=headers)
    _ = client.get(f"{APPROVALS_BASE}/{approval['approval_id']}/quorum-status", headers=headers)
    _ = client.get(f"{APPROVALS_BASE}/{approval['approval_id']}/votes", headers=headers)
    _ = client.get(f"{INTENTS_BASE}/{intent['intent_id']}/readiness", headers=headers)

    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    assert after_audit == before_audit
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews
    assert after_signals == before_signals

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_approval_policies" in groups
    assert "governance_autopilot_approval_votes" in groups
    assert "governance_autopilot_approval_quorum" in groups

    # write-side audits
    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action.like("governance_autopilot_approval_policy.%"),
            )
        ).all()
    }
    assert "governance_autopilot_approval_policy.created" in actions

    write_actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action.like("governance_autopilot_execution_approval.%"),
            )
        ).all()
    }
    assert "governance_autopilot_execution_approval.requested" in write_actions

    # no hard delete
    approval_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecutionApproval.id)).where(
                GovernanceAutopilotExecutionApproval.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    vote_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecutionApprovalVote.id)).where(
                GovernanceAutopilotExecutionApprovalVote.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    assert approval_rows >= 1
    assert vote_rows >= 0
