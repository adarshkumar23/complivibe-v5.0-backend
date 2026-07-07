import uuid

from sqlalchemy import func, select

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.email_outbox import EmailOutbox
from app.models.governance_autopilot_execution import GovernanceAutopilotExecution
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_policies_phase70 import POLICY_BASE, _seed

INTENTS_BASE = "/api/v1/ai-governance/autopilot/execution-intents"
EXECUTIONS_BASE = "/api/v1/ai-governance/autopilot/executions"


def _set_autopilot_settings(client, headers: dict[str, str], *, enabled: bool, threshold: float = 0.95) -> None:
    resp = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=headers,
        json={
            "autopilot_auto_execute_enabled": enabled,
            "autopilot_auto_execute_confidence_threshold": threshold,
            "autopilot_auto_execute_reversal_window_hours": 24,
        },
    )
    assert resp.status_code == 200


def _policy_allow_auto(client, headers: dict[str, str]) -> str:
    resp = client.post(
        POLICY_BASE,
        headers=headers,
        json={
            "name": "phase76-auto",
            "mode": "suggest_only",
            "status": "active",
            "is_default": True,
            "external_effects_allowed": True,
            "source_record_mutation_allowed": True,
        },
    )
    assert resp.status_code == 201
    return resp.json()["policy_id"]


def _candidate(*, assessment_id: str, ai_system_id: str, risk_tier: str, confidence_score: float, action_key: str = "send_reminder", action_type: str = "refresh_signals") -> dict:
    return {
        "action_key": action_key,
        "title": "Phase76 candidate",
        "description": "Phase76 deterministic candidate",
        "action_type": action_type,
        "priority_score": 90,
        "priority_band": "low",
        "source_signal_ids": [],
        "source_reason_codes": ["classification_needs_review"],
        "target_entity_type": "risk_assessment",
        "target_entity_id": assessment_id,
        "related_ai_system_id": ai_system_id,
        "related_risk_assessment_id": assessment_id,
        "rationale": "test",
        "rationale_json": {},
        "human_approval_required": False,
        "automation_allowed": True,
        "target_route_hint": None,
        "risk_tier": risk_tier,
        "confidence_score": confidence_score,
    }


def _create_intent(client, headers: dict[str, str], *, policy_id: str, candidate: dict) -> dict:
    resp = client.post(
        INTENTS_BASE,
        headers=headers,
        json={
            "source_type": "candidate_action",
            "candidate_action_json": candidate,
            "policy_id": policy_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _execution_for_intent(client, headers: dict[str, str], *, intent_id: str) -> dict | None:
    resp = client.get(
        EXECUTIONS_BASE,
        headers=headers,
        params={"execution_intent_id": intent_id},
    )
    assert resp.status_code == 200
    rows = resp.json()
    return rows[0] if rows else None


def test_phase76_low_risk_high_confidence_auto_executes_and_reverses_with_notification(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p76-auto")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-Auto")
    # Server-side confidence is always AUTOPILOT_DEFAULT_CONFIDENCE_SCORE (0.5),
    # never the client-supplied value (see security fix below), so the org must
    # explicitly opt into a threshold at/below that default for auto-exec to fire.
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.5)
    policy_id = _policy_allow_auto(client, headers)

    before_assessment = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    before_factors = dict(before_assessment.risk_factors_json or {}) if isinstance(before_assessment.risk_factors_json, dict) else {}
    before_email_count = int(
        db_session.execute(
            select(func.count(EmailOutbox.id)).where(
                EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
                EmailOutbox.event_type == "autopilot.auto_execution",
            )
        ).scalar_one()
    )

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
    assert execution["execution_status"] == "executed"
    assert execution["risk_tier"] == "low"
    # Client claimed confidence_score=0.99; server must ignore it and persist its
    # own server-derived default instead of trusting client self-attestation.
    assert execution["confidence_score"] == 0.5

    after_assessment = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    assert after_assessment.risk_factors_json != before_factors
    after_email_count = int(
        db_session.execute(
            select(func.count(EmailOutbox.id)).where(
                EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
                EmailOutbox.event_type == "autopilot.auto_execution",
            )
        ).scalar_one()
    )
    assert after_email_count > before_email_count

    reverse = client.post(
        f"{EXECUTIONS_BASE}/{execution['execution_id']}/reverse",
        headers=headers,
        json={"reason": "test reverse"},
    )
    assert reverse.status_code == 200
    reversed_body = reverse.json()
    assert reversed_body["execution_status"] == "reversed"
    restored = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    assert (restored.risk_factors_json or {}) == before_factors


def test_phase76_high_risk_never_auto_executes_even_at_full_confidence(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p76-high")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-High")
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.95)
    policy_id = _policy_allow_auto(client, headers)

    intent = _create_intent(
        client,
        headers,
        policy_id=policy_id,
        candidate=_candidate(
            assessment_id=assessment["id"],
            ai_system_id=ai["id"],
            risk_tier="high",
            confidence_score=1.0,
            action_key="delete_evidence",
            action_type="refresh_signals",
        ),
    )
    assert intent["intent_status"] == "approval_required"
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


def test_phase76_low_confidence_low_risk_requires_approval(client):
    org = bootstrap_org_user(client, email_prefix="p76-lowconf")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-LowConf")
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
            confidence_score=0.2,
            action_key="send_reminder",
            action_type="refresh_signals",
        ),
    )
    assert intent["intent_status"] == "approval_required"
    assert _execution_for_intent(client, headers, intent_id=intent["intent_id"]) is None


def test_phase76_opt_out_org_never_auto_executes(client):
    org = bootstrap_org_user(client, email_prefix="p76-optout")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-OptOut")
    _set_autopilot_settings(client, headers, enabled=False, threshold=0.95)
    policy_id = _policy_allow_auto(client, headers)

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
    assert _execution_for_intent(client, headers, intent_id=intent["intent_id"]) is None


def test_phase76_circuit_breaker_trips_and_disables_auto_execute(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p76-breaker")
    headers = org["org_headers"]
    ai, assessment, _ = _seed(client, headers, name="P76-Breaker")
    _set_autopilot_settings(client, headers, enabled=True, threshold=0.5)
    policy_id = _policy_allow_auto(client, headers)

    execution_ids: list[str] = []
    for _ in range(5):
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

    reverse_1 = client.post(f"{EXECUTIONS_BASE}/{execution_ids[0]}/reverse", headers=headers, json={"reason": "r1"})
    assert reverse_1.status_code == 200
    reverse_2 = client.post(f"{EXECUTIONS_BASE}/{execution_ids[1]}/reverse", headers=headers, json={"reason": "r2"})
    assert reverse_2.status_code == 200

    settings = client.get("/api/v1/organizations/me/governance-settings", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["autopilot_auto_execute_enabled"] is False

    settings_row = db_session.execute(
        select(OrganizationGovernanceSetting).where(
            OrganizationGovernanceSetting.organization_id == uuid.UUID(org["organization_id"])
        )
    ).scalar_one()
    assert settings_row.autopilot_auto_execute_enabled is False
