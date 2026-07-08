from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_guardrail_event import AIGuardrailEvent
from app.models.ai_policy_guardrail import AIPolicyGuardrail
from app.models.ai_system import AISystem
from app.models.ai_system_risk_link import AISystemRiskLink
from app.models.control import Control
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from tests.helpers.auth_org import bootstrap_org_user

DASHBOARD_URL = "/api/v1/ai-governance/dashboard"


def test_dashboard_governance_coverage_from_approved_envelope(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dash-coverage-env")
    org_id = uuid.UUID(org["organization_id"])
    owner_id = uuid.UUID(org["user_id"])

    system = AISystem(
        organization_id=org_id,
        name="Covered System",
        system_type="model",
        risk_tier="high",
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    db_session.add(system)
    db_session.flush()

    envelope = AIApprovalEnvelope(
        organization_id=org_id,
        ai_system_id=system.id,
        transition_from="development",
        transition_to="production",
        required_approvers=[str(owner_id)],
        approvals_received={},
        conditions=[],
        status="approved",
        expires_at=datetime.now(UTC),
        created_by=owner_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(envelope)
    db_session.commit()

    response = client.get(DASHBOARD_URL, headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["governance_coverage_pct"] == 100.0
    assert body["ai_systems_by_tier"]["high"] == 1


def test_dashboard_governance_coverage_from_risk_control_link(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dash-coverage-link")
    org_id = uuid.UUID(org["organization_id"])
    owner_id = uuid.UUID(org["user_id"])

    system = AISystem(
        organization_id=org_id,
        name="Linked System",
        system_type="model",
        risk_tier="medium",
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    db_session.add(system)
    db_session.flush()

    risk = Risk(
        organization_id=org_id,
        title="Model drift",
        category="ai",
        severity="medium",
        owner_user_id=owner_id,
    )
    db_session.add(risk)
    db_session.flush()

    control = Control(
        organization_id=org_id,
        title="Drift monitoring control",
        status="active",
    )
    db_session.add(control)
    db_session.flush()

    ai_risk_link = AISystemRiskLink(
        organization_id=org_id,
        ai_system_id=system.id,
        risk_id=risk.id,
        status="active",
    )
    db_session.add(ai_risk_link)

    risk_control_link = RiskControlLink(
        organization_id=org_id,
        risk_id=risk.id,
        control_id=control.id,
        status="active",
    )
    db_session.add(risk_control_link)
    db_session.commit()

    response = client.get(DASHBOARD_URL, headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["governance_coverage_pct"] == 100.0
    assert body["ai_systems_by_tier"]["medium"] == 1


def test_dashboard_policy_violations_from_guardrail_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dash-violations")
    org_id = uuid.UUID(org["organization_id"])
    owner_id = uuid.UUID(org["user_id"])

    system = AISystem(
        organization_id=org_id,
        name="Guardrailed System",
        system_type="model",
        risk_tier="high",
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    db_session.add(system)
    db_session.flush()

    guardrail = AIPolicyGuardrail(
        organization_id=org_id,
        ai_system_id=system.id,
        guardrail_type="data_scope",
        constraint_description="Limit PII use",
        violation_action="block_and_alert",
        created_by=owner_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(guardrail)
    db_session.flush()

    for event_type in ("violation_detected", "blocked"):
        db_session.add(
            AIGuardrailEvent(
                organization_id=org_id,
                guardrail_id=guardrail.id,
                ai_system_id=system.id,
                event_type=event_type,
                context_json={"reason": "test"},
                created_at=datetime.now(UTC),
            )
        )
    db_session.commit()

    response = client.get(DASHBOARD_URL, headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["policy_violations_count"] == 2


def test_dashboard_tier_counts_include_unassessed_and_non_internal_tiers(client, db_session):
    """G9 item 3: systems with no risk_tier, or a tier outside the internal
    critical/high/medium/low set (e.g. an EU AI Act tier like "minimal"), must
    still be counted -- not silently dropped from ai_systems_by_tier."""
    org = bootstrap_org_user(client, email_prefix="dash-tier-unassessed")
    org_id = uuid.UUID(org["organization_id"])
    owner_id = uuid.UUID(org["user_id"])

    unassessed_1 = AISystem(
        organization_id=org_id,
        name="No Tier System A",
        system_type="model",
        risk_tier=None,
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    unassessed_2 = AISystem(
        organization_id=org_id,
        name="No Tier System B",
        system_type="model",
        risk_tier=None,
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    eu_act_tier = AISystem(
        organization_id=org_id,
        name="Minimal Risk System",
        system_type="model",
        risk_tier="minimal",
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    db_session.add_all([unassessed_1, unassessed_2, eu_act_tier])
    db_session.commit()

    response = client.get(DASHBOARD_URL, headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    by_tier = body["ai_systems_by_tier"]
    assert by_tier["unassessed"] == 2
    assert by_tier["minimal"] == 1
    assert sum(by_tier.values()) == 3


def test_dashboard_policy_violations_proxy_from_monitoring_readings(client, db_session):
    from app.models.ai_monitoring_config import AIMonitoringConfig
    from app.models.ai_monitoring_reading import AIMonitoringReading
    from decimal import Decimal

    org = bootstrap_org_user(client, email_prefix="dash-proxy")
    org_id = uuid.UUID(org["organization_id"])
    owner_id = uuid.UUID(org["user_id"])

    system = AISystem(
        organization_id=org_id,
        name="Monitored System",
        system_type="model",
        risk_tier="low",
        created_by=owner_id,
        created_by_user_id=owner_id,
    )
    db_session.add(system)
    db_session.flush()

    config = AIMonitoringConfig(
        organization_id=org_id,
        ai_system_id=system.id,
        metric_type="accuracy",
        threshold_value=Decimal("0.9"),
        comparison_direction="above",
        created_by=owner_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(config)
    db_session.flush()

    db_session.add(
        AIMonitoringReading(
            organization_id=org_id,
            config_id=config.id,
            value=Decimal("0.7"),
            reading_source="manual",
            within_threshold=False,
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    response = client.get(DASHBOARD_URL, headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["policy_violations_count"] == 1
