"""Adversarial reproductions from the independent verification report.

Each test reproduces the EXACT attack described in the verification findings
and asserts it is now blocked:

  1. risk_tier bypass: claiming risk_tier="low" for a destructive/high-risk
     action_key (delete_evidence) must not skip human approval.
  2. confidence_score self-attestation: claiming confidence_score=1.0 must not
     be trusted as the sole determinant of auto-execution.
  3. circuit breaker evasion: 4/4 reversals within a window smaller than the
     old minimum sample size (5) must now trip the breaker.
"""

import uuid

from sqlalchemy import func, select

from app.models.governance_autopilot_execution import GovernanceAutopilotExecution
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_auto_execution_phase76 import (
    _candidate,
    _create_intent,
    _execution_for_intent,
    _policy_allow_auto,
    _set_autopilot_settings,
)
from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed

INTENTS_BASE = "/api/v1/ai-governance/autopilot/execution-intents"
EXECUTIONS_BASE = "/api/v1/ai-governance/autopilot/executions"


def test_fix1_delete_evidence_claimed_low_risk_still_requires_approval(client, db_session):
    """Reproduction: attacker submits action_key="delete_evidence" with a
    self-declared risk_tier="low" to try to skip the high-risk approval gate
    and get it auto-executed. The server must ignore the claimed risk_tier and
    derive it itself from action_key/action_type."""
    org = bootstrap_org_user(client, email_prefix="secfix-risktier")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="SecFix-RiskTier")
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.0)
    policy_id = _policy_allow_auto(client, headers)

    intent = _create_intent(
        client,
        headers,
        policy_id=policy_id,
        candidate=_candidate(
            assessment_id=assessment["id"],
            ai_system_id=ai["id"],
            risk_tier="low",  # attacker-claimed, must be ignored
            confidence_score=1.0,  # attacker-claimed, must be ignored
            action_key="delete_evidence",
            action_type="update_record",
        ),
    )

    # The server must have re-derived risk_tier server-side as "high" and must
    # never let this reach "planned" (the status that allows auto-execution),
    # regardless of the client's claimed risk_tier="low".
    assert intent["intent_status"] in ("approval_required", "blocked")

    execution = _execution_for_intent(client, headers, intent_id=intent["intent_id"])
    assert execution is None

    rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecution.id)).where(
                GovernanceAutopilotExecution.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    assert rows == 0


def test_fix2_self_attested_full_confidence_cannot_force_auto_execution(client, db_session):
    """Reproduction: attacker submits confidence_score=1.0 directly via the API
    for what would otherwise be a low-confidence scenario, to try to force
    auto-execution past the org's confidence threshold. The server must never
    trust a client-supplied confidence_score for this decision."""
    org = bootstrap_org_user(client, email_prefix="secfix-confidence")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="SecFix-Confidence")
    # Threshold above the server's true internal default (0.5) -- if the
    # attacker's claimed confidence_score=1.0 were trusted, this would auto-execute.
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.95)
    policy_id = _policy_allow_auto(client, headers)

    intent = _create_intent(
        client,
        headers,
        policy_id=policy_id,
        candidate=_candidate(
            assessment_id=assessment["id"],
            ai_system_id=ai["id"],
            risk_tier="low",
            confidence_score=1.0,  # attacker-claimed, must be ignored
            action_key="send_reminder",
            action_type="refresh_signals",
        ),
    )

    assert intent["intent_status"] == "approval_required"
    execution = _execution_for_intent(client, headers, intent_id=intent["intent_id"])
    assert execution is None


def test_fix3_circuit_breaker_trips_on_4_of_4_reversals_under_old_min_sample(client, db_session):
    """Reproduction: 4 auto-executions, all 4 reversed (100% reversal rate),
    staying under the old AUTOPILOT_CIRCUIT_BREAKER_MIN_SAMPLE_SIZE of 5 so the
    breaker never evaluated the reversal-rate threshold. The breaker must now
    trip on this exact scenario."""
    org = bootstrap_org_user(client, email_prefix="secfix-breaker")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="SecFix-Breaker")
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.5)
    policy_id = _policy_allow_auto(client, headers)

    execution_ids: list[str] = []
    for _ in range(4):
        intent = _create_intent(
            client,
            headers,
            policy_id=policy_id,
            candidate=_candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                risk_tier="low",
                confidence_score=0.99,
                action_key="send_reminder",
                action_type="refresh_signals",
            ),
        )
        execution = _execution_for_intent(client, headers, intent_id=intent["intent_id"])
        assert execution is not None
        execution_ids.append(execution["execution_id"])

    for execution_id in execution_ids:
        reverse = client.post(
            f"{EXECUTIONS_BASE}/{execution_id}/reverse",
            headers=headers,
            json={"reason": "secfix reverse"},
        )
        assert reverse.status_code == 200

    settings_row = db_session.execute(
        select(OrganizationGovernanceSetting).where(
            OrganizationGovernanceSetting.organization_id == uuid.UUID(org["organization_id"])
        )
    ).scalar_one()
    assert settings_row.autopilot_auto_execute_enabled is False


def test_fix4_auto_execution_blocked_when_no_active_admin_to_notify(client, db_session):
    """An org with zero active owner/admin members must not be able to have an
    auto-execution happen silently with notification_count == 0.

    Auth requires an active membership to call the API at all, so this drives
    the scenario at the service layer (sharing the same DB session/transaction
    as `client`, per tests/conftest.py) after deactivating the sole owner
    membership -- the exact condition `_auto_execute_candidate_action` guards
    against.
    """
    from fastapi import HTTPException

    from app.models.membership import Membership
    from app.services.ai_system_risk_assessment_service import AISystemRiskAssessmentService

    org = bootstrap_org_user(client, email_prefix="secfix-noadmin")
    headers = org["org_headers"]
    organization_id = uuid.UUID(org["organization_id"])
    ai, assessment, _ = _seed(client, headers, name="SecFix-NoAdmin")
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.5)
    policy_id = _policy_allow_auto(client, headers)

    db_session.execute(
        Membership.__table__.update()
        .where(Membership.organization_id == organization_id)
        .values(status="inactive")
    )
    db_session.flush()

    service = AISystemRiskAssessmentService(db_session)
    raised = False
    try:
        service.create_execution_intent(
            organization_id=organization_id,
            source_type="candidate_action",
            source_id=None,
            candidate_action_json=_candidate(
                assessment_id=assessment["id"],
                ai_system_id=ai["id"],
                risk_tier="low",
                confidence_score=0.99,
                action_key="send_reminder",
                action_type="refresh_signals",
            ),
            policy_id=uuid.UUID(policy_id),
            actor_user_id=None,
        )
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 409

    assert raised, "expected auto-execution to be blocked when no active admin exists"

    rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecution.id)).where(
                GovernanceAutopilotExecution.organization_id == organization_id
            )
        ).scalar_one()
    )
    assert rows == 0
