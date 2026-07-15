from __future__ import annotations

"""Phase 5 -- Autopilot cross-domain graph-aware reasoning (safety-critical).

Most tests run on the SQLite unit harness (the autopilot engine is DB-agnostic;
source B's PG-only graph traversal is covered separately in
tests/integration/test_autopilot_graph_reasoning_pg.py). The adversarial
corroboration test (constraint #4) is the most important assertion in the phase.
"""

import ast
import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from app.services.ai_system_risk_assessment_service import (
    AUTOPILOT_DEFAULT_CONFIDENCE_SCORE,
    AISystemRiskAssessmentService,
)
from tests.helpers.auth_org import bootstrap_org_user


# --------------------------------------------------------------------------- #
# Structural guarantees (§2, #1) -- no DB needed
# --------------------------------------------------------------------------- #
def _calls(method) -> set[str]:
    tree = ast.parse(inspect.getsource(method).strip())
    return {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}


def test_cross_domain_methods_make_no_auto_execute_call():
    for method in (
        AISystemRiskAssessmentService.create_cross_domain_execution_intent,
        AISystemRiskAssessmentService.generate_cross_domain_candidate_actions,
        AISystemRiskAssessmentService.generate_and_route_cross_domain_candidates,
    ):
        calls = _calls(method)
        assert "_auto_execute_candidate_action" not in calls, f"{method.__name__} must never call auto-execute"
        assert "_should_auto_execute_action" not in calls, f"{method.__name__} must never call the auto-execute gate"


def test_auto_execute_path_refuses_cross_domain_source_type(db_session):
    svc = AISystemRiskAssessmentService(db_session)
    with pytest.raises(HTTPException) as exc:
        svc.create_execution_intent(
            organization_id=uuid.uuid4(), source_type="cross_domain_candidate_action",
            source_id=None, candidate_action_json={}, policy_id=None, actor_user_id=None,
        )
    assert exc.value.status_code == 400
    assert "suggestion-only" in exc.value.detail


def test_cross_domain_rejects_non_allowlisted_action(db_session):
    svc = AISystemRiskAssessmentService(db_session)
    with pytest.raises(HTTPException) as exc:
        svc.create_cross_domain_execution_intent(
            organization_id=uuid.uuid4(), actor_user_id=None,
            candidate_action_json={"candidate_source": "compound_insight", "action_key": "delete_evidence",
                                   "action_type": "delete_record", "priority_band": "low", "source_reason_codes": ["x"]},
        )
    assert exc.value.status_code == 400  # allowlist blocks destructive action before any DB touch


# --------------------------------------------------------------------------- #
# Seed helpers (SQLite via db_session)
# --------------------------------------------------------------------------- #
def _enable_graph_reasoning(db, org_id):
    row = db.execute(
        select(OrganizationGovernanceSetting).where(OrganizationGovernanceSetting.organization_id == org_id)
    ).scalar_one_or_none()
    if row is None:
        row = OrganizationGovernanceSetting(organization_id=org_id, autopilot_graph_reasoning_enabled=True)
        db.add(row)
    else:
        row.autopilot_graph_reasoning_enabled = True
    db.flush()
    return row


def _compound_insight(db, org_id, *, control_id, severity="critical"):
    from app.models.compound_insight import CompoundInsight

    ins = CompoundInsight(
        organization_id=org_id, pattern_id="failed_control_stale_vendor_open_risk", severity=severity,
        status="surfaced", dedup_key=uuid.uuid4().hex, title="Compound exposure",
        templated_narrative="Control failed; vendor stale; open risk.", narrative_source="template",
        matched_nodes_json={"anchor": {"entity_type": "control", "entity_id": str(control_id), "label": "C"}},
    )
    db.add(ins); db.flush(); return ins


def _control_health_snap(db, org_id, *, impl, at):
    from app.models.score_snapshot import ScoreSnapshot

    bd = {"implemented_ratio": impl, "latest_test_pass_ratio": 0.0, "needs_review_ratio": 0.0, "open_high_critical_issue_ratio": 0.0}
    r = ScoreSnapshot(organization_id=org_id, snapshot_type="control_health", score=round(55 * impl),
                      grade="C", inputs_json={}, breakdown_json=bd, calculated_at=at)
    db.add(r); db.flush(); return r


def _control(db, org_id):
    from app.models.control import Control

    c = Control(organization_id=org_id, title="C", status="failed"); db.add(c); db.flush(); return c


def _control_event(db, org_id, control_id, at):
    from app.models.domain_event import DomainEvent

    e = DomainEvent(organization_id=org_id, event_type="control.status_changed", entity_type="control",
                    entity_id=control_id, previous_value="implemented", new_value="failed",
                    triggered_by="test", occurred_at=at)
    db.add(e); db.flush(); return e


# --------------------------------------------------------------------------- #
# Source A + create-intent: approval-only
# --------------------------------------------------------------------------- #
def test_source_a_compound_insight_generates_approval_only_candidate(client, db_session):
    org = bootstrap_org_user(client, email_prefix="gr-a")
    org_id = uuid.UUID(org["organization_id"])
    control = _control(db_session, org_id)
    _compound_insight(db_session, org_id, control_id=control.id)
    _enable_graph_reasoning(db_session, org_id)
    db_session.commit()

    svc = AISystemRiskAssessmentService(db_session)
    candidates = svc.generate_cross_domain_candidate_actions(organization_id=org_id)
    a = [c for c in candidates if c["candidate_source"] == "compound_insight"]
    assert len(a) == 1
    assert a[0]["action_key"] == "send_reminder"  # one of the 3 allow-listed low-risk actions
    assert a[0]["automation_allowed"] is False

    intent = svc.create_cross_domain_execution_intent(
        organization_id=org_id, candidate_action_json=a[0], actor_user_id=None,
    )
    db_session.commit()
    assert intent.source_type == "cross_domain_candidate_action"
    assert intent.intent_status == "approval_required"  # NEVER auto-executed
    assert intent.approval_required is True and intent.blocked is False
    plan = intent.plan_payload_json
    assert plan["candidate_action"]["risk_tier"] == "low"
    assert plan["auto_execute"]["eligible"] is False and plan["auto_execute"]["structurally_gated"] is True


def test_source_c_score_attribution_generates_reminder_for_real_cause(client, db_session):
    org = bootstrap_org_user(client, email_prefix="gr-c")
    org_id = uuid.UUID(org["organization_id"])
    control = _control(db_session, org_id)
    t1 = datetime.now(UTC) - timedelta(hours=3)
    t2 = datetime.now(UTC) - timedelta(hours=1)
    _control_health_snap(db_session, org_id, impl=0.8, at=t1)   # score 44
    _control_health_snap(db_session, org_id, impl=0.4, at=t2)   # score 22 (a real drop)
    _control_event(db_session, org_id, control.id, datetime.now(UTC) - timedelta(hours=2))
    _enable_graph_reasoning(db_session, org_id)
    db_session.commit()

    svc = AISystemRiskAssessmentService(db_session)
    candidates = svc.generate_cross_domain_candidate_actions(organization_id=org_id)
    c = [x for x in candidates if x["candidate_source"] == "score_attribution"]
    assert c, "expected a score-attribution candidate"
    assert all(x["action_key"] == "send_reminder" for x in c)
    assert any(str(control.id) == str(x["target_entity_id"]) for x in c)  # targets the REAL cause entity


# --------------------------------------------------------------------------- #
# THE adversarial test (constraint #4): corroboration must NOT change the gate.
# --------------------------------------------------------------------------- #
def test_corroboration_never_changes_auto_execute_eligibility(client, db_session):
    org = bootstrap_org_user(client, email_prefix="gr-adv")
    org_id = uuid.UUID(org["organization_id"])
    _enable_graph_reasoning(db_session, org_id)
    db_session.commit()
    svc = AISystemRiskAssessmentService(db_session)

    base = {
        "candidate_source": "compound_insight", "action_key": "send_reminder", "action_type": "send_reminder",
        "priority_band": "high", "source_reason_codes": ["compound_insight_surfaced"],
        "target_entity_type": "control", "target_entity_id": str(uuid.uuid4()), "automation_allowed": False,
    }
    # Adversarial: strong cross-domain corroboration AND a smuggled confidence of 1.0.
    corroborated = {
        **base,
        "confidence_score": 1.0,  # attempt to smuggle a high confidence
        "human_review_context": {"corroborating_sources": ["compound_insight", "graph_dependency", "score_attribution"],
                                 "corroboration_count": 3, "details": [{"x": 1}, {"y": 2}, {"z": 3}]},
    }
    plain = {**base}

    # 1. The validated confidence is FORCED to the internal default in BOTH cases --
    #    corroboration / smuggled 1.0 is discarded before it can reach the gate.
    v_corr = svc._validate_candidate_action_shape(candidate_action_json=corroborated)
    v_plain = svc._validate_candidate_action_shape(candidate_action_json=plain)
    assert v_corr["confidence_score"] == AUTOPILOT_DEFAULT_CONFIDENCE_SCORE == 0.5
    assert v_plain["confidence_score"] == AUTOPILOT_DEFAULT_CONFIDENCE_SCORE
    assert v_corr["risk_tier"] == v_plain["risk_tier"] == "low"

    # 2. The auto-execute gate outcome is IDENTICAL with and without corroboration.
    policy_preview = {"allowed_by_policy": True, "requires_human_approval": False}
    gate_corr = svc._should_auto_execute_action(organization_id=org_id, action=v_corr, policy_preview=policy_preview)
    gate_plain = svc._should_auto_execute_action(organization_id=org_id, action=v_plain, policy_preview=policy_preview)
    assert gate_corr == gate_plain
    assert gate_corr[0] is False  # not eligible (confidence 0.5 < 0.95, not opted in, etc.)

    # 3. And routing it lands in approval_required regardless of the corroboration.
    intent = svc.create_cross_domain_execution_intent(
        organization_id=org_id, candidate_action_json=corroborated, actor_user_id=None,
    )
    db_session.commit()
    assert intent.intent_status == "approval_required"
    # corroboration is preserved ONLY in human_review_context, never in the gated fields.
    assert intent.plan_payload_json["human_review_context"]["corroboration_count"] == 3
    assert intent.plan_payload_json["candidate_action"]["confidence_score"] == 0.5


# --------------------------------------------------------------------------- #
# Kill-switch (#5)
# --------------------------------------------------------------------------- #
def test_kill_switch_off_generates_nothing(client, db_session):
    org = bootstrap_org_user(client, email_prefix="gr-ks")
    org_id = uuid.UUID(org["organization_id"])
    control = _control(db_session, org_id)
    _compound_insight(db_session, org_id, control_id=control.id)  # data exists...
    # ...but the kill-switch defaults OFF (no settings row / flag false).
    db_session.commit()
    svc = AISystemRiskAssessmentService(db_session)
    assert svc.generate_cross_domain_candidate_actions(organization_id=org_id) == []
    assert svc.generate_and_route_cross_domain_candidates(organization_id=org_id, actor_user_id=None) == []

    # Flipping it on with the same data now yields candidates (proves it was the gate).
    _enable_graph_reasoning(db_session, org_id)
    db_session.commit()
    assert len(svc.generate_cross_domain_candidate_actions(organization_id=org_id)) >= 1


def test_kill_switch_does_not_affect_base_autopilot(client, db_session):
    """Base Autopilot candidate generation must not depend on the new flag."""
    src = inspect.getsource(AISystemRiskAssessmentService._build_real_execution_signal_candidates)
    assert "autopilot_graph_reasoning_enabled" not in src


# --------------------------------------------------------------------------- #
# voter_user_id=None hardening (#6)
# --------------------------------------------------------------------------- #
def test_voter_none_is_rejected_outright(client, db_session):
    from app.models.governance_autopilot_execution_approval import GovernanceAutopilotExecutionApproval
    from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent

    org = bootstrap_org_user(client, email_prefix="gr-voter")
    org_id = uuid.UUID(org["organization_id"])
    intent = GovernanceAutopilotExecutionIntent(
        organization_id=org_id, source_type="candidate_action", source_id=None, policy_id=None,
        intent_status="approval_required", plan_payload_json={}, capability_decisions_json={},
        approval_required=True, blocked=False, blocked_reasons_json=[], source_entities_json={},
        source_hash="h", intent_sha256="s", created_by_user_id=None,
    )
    db_session.add(intent); db_session.flush()
    approval = GovernanceAutopilotExecutionApproval(
        organization_id=org_id, execution_intent_id=intent.id, approval_status="requested",
        requested_by_user_id=None, requested_at=datetime.now(UTC),
        approval_policy_snapshot_json={"block_requester_self_approval": True},
        approval_requirements_json={}, readiness_snapshot_json={},
    )
    db_session.add(approval); db_session.flush()

    svc = AISystemRiskAssessmentService(db_session)
    with pytest.raises(HTTPException) as exc:
        svc.vote_approve_execution_approval(
            organization_id=org_id, approval_id=approval.id, vote_reason="r", vote_note=None, actor_user_id=None,
        )
    assert exc.value.status_code == 400
    assert "distinct approver identity is required" in exc.value.detail.lower()


# --------------------------------------------------------------------------- #
# Audit-trail gaps (#7) -- via the real auto-exec / circuit-breaker path
# --------------------------------------------------------------------------- #
def _drive_auto_exec(client, db_session):
    from tests.unit.test_ai_system_autopilot_auto_execution_phase76 import (
        _candidate,
        _create_intent,
        _policy_allow_auto,
        _set_autopilot_settings,
    )
    from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed

    org = bootstrap_org_user(client, email_prefix="gr-audit")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="GR-Audit")
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.5)
    policy_id = _policy_allow_auto(client, headers)
    intent = _create_intent(client, headers, policy_id=policy_id, candidate=_candidate(
        assessment_id=assessment["id"], ai_system_id=ai["id"], risk_tier="low", confidence_score=0.99,
        action_key="send_reminder", action_type="refresh_signals"))
    return org, headers, intent


def test_execution_executed_audit_entry_now_exists(client, db_session):
    org, _headers, intent = _drive_auto_exec(client, db_session)
    org_id = uuid.UUID(org["organization_id"])
    count = int(db_session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "governance_autopilot_execution.executed",
        )
    ).scalar_one())
    assert count >= 1  # the previously-missing execution.executed audit entry


def test_circuit_breaker_trip_writes_audit_entry(client, db_session):
    from app.models.governance_autopilot_execution import GovernanceAutopilotExecution
    from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent

    org = bootstrap_org_user(client, email_prefix="gr-cb")
    org_id = uuid.UUID(org["organization_id"])
    settings = _enable_graph_reasoning(db_session, org_id)
    settings.autopilot_auto_execute_enabled = True
    db_session.flush()
    intent = GovernanceAutopilotExecutionIntent(
        organization_id=org_id, source_type="candidate_action", source_id=None, policy_id=None,
        intent_status="planned", plan_payload_json={}, capability_decisions_json={}, approval_required=False,
        blocked=False, blocked_reasons_json=[], source_entities_json={}, source_hash="h", intent_sha256="s2",
        created_by_user_id=None)
    db_session.add(intent); db_session.flush()
    now = datetime.now(UTC)
    for i in range(3):  # 3 executions, 1 reversed -> 33% reversal rate > 20% -> trips
        db_session.add(GovernanceAutopilotExecution(
            organization_id=org_id, execution_intent_id=intent.id, action_key="send_reminder",
            action_type="refresh_signals", risk_tier="low", execution_status="executed" if i else "reversed",
            before_snapshot_json={}, after_snapshot_json={}, reversal_deadline_at=now + timedelta(hours=24),
            created_at=now, reversed_at=(now if i == 0 else None)))
    db_session.flush()

    svc = AISystemRiskAssessmentService(db_session)
    svc._run_autopilot_circuit_breaker(organization_id=org_id, actor_user_id=None)
    db_session.flush()

    db_session.refresh(settings)
    assert settings.autopilot_auto_execute_enabled is False  # tripped
    count = int(db_session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "governance_autopilot_circuit_breaker.tripped",
        )
    ).scalar_one())
    assert count == 1  # the previously-missing circuit-breaker-trip audit entry
