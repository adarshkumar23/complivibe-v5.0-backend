"""P4 end to end: satellite push -> reading -> tier evaluation -> decision -> dispatch.

Two halves:

  * the tiered path now reachable from Feature #66's own submit_reading, WITHOUT
    changing what a single-config reading does (that invariant lives in
    test_ai_monitoring_feature66_characterization.py);
  * the full external route, from a scoped-key-authenticated HTTP push through to a
    dispatched governance workflow -- the path P4 was designed for, exercised as one
    piece for the first time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.ai_governance.services.governance_graph.scoped_key_service import PatentScopedKeyService
from app.models.ai_monitoring_breach_event import AIMonitoringBreachEvent
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.audit_log import AuditLog
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.organization import Organization
from app.models.user import User

P4_PUSH = "/api/v1/patent-ingest/p4/monitoring-reading"


def _config(org_id, system_id, user_id, *, tier, order, workflow, threshold, metric="accuracy"):
    now = datetime.now(UTC)
    return AIMonitoringConfig(
        id=uuid.uuid4(),
        organization_id=org_id,
        ai_system_id=system_id,
        metric_type=metric,
        threshold_value=Decimal(threshold),
        comparison_direction="below",
        alert_on_breach=True,
        is_active=True,
        created_by=user_id,
        created_at=now,
        updated_at=now,
        api_key_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        tier=tier,
        escalation_order=order,
        threshold_operator="lte",
        workflow_to_trigger=workflow,
    )


@pytest.fixture()
def org_env(db_session):
    org = Organization(id=uuid.uuid4(), name="P4 E2E Org")
    user = User(
        id=uuid.uuid4(),
        email=f"e2e-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    system = AISystem(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Fraud Model",
        system_type="internal_model",
        lifecycle_status="production",
    )
    db_session.add_all([org, user, system])
    db_session.flush()
    return {"org": org, "user": user, "system": system}


# ================================================ submit_reading, multi-tier (item 3b)


def test_multi_tier_config_dispatches_every_breached_sibling(db_session, org_env):
    """The new capability: additional tiers beyond the submitted config all fire."""
    submitted = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="default", order=0, workflow="create_alert", threshold="0.9500",
    )
    warning = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="warning", order=1, workflow="create_alert", threshold="0.9000",
    )
    critical = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="critical", order=2, workflow="notify_oncall", threshold="0.8500",
    )
    db_session.add_all([submitted, warning, critical])
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        org_env["org"].id, submitted.id, Decimal("0.8100"), "api_report", "evidently"
    )

    events = db_session.execute(
        select(AIMonitoringBreachEvent).where(
            AIMonitoringBreachEvent.organization_id == org_env["org"].id
        )
    ).scalars().all()
    # The submitted config keeps Feature #66's behaviour and records no breach event;
    # the two SIBLING tiers each record and dispatch their own.
    assert {e.tier for e in events} == {"warning", "critical"}
    assert all(e.workflow_reference is not None for e in events)

    alerts = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.organization_id == org_env["org"].id
        )
    ).scalars().all()
    # One legacy Feature #66 alert + one per breached sibling tier.
    assert len(alerts) == 3
    assert {a.alert_type for a in alerts} == {"ai_monitoring", "ai_monitoring_oncall"}


def test_sibling_tier_that_was_not_breached_does_not_dispatch(db_session, org_env):
    submitted = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="default", order=0, workflow="create_alert", threshold="0.9500",
    )
    unbreached = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="critical", order=1, workflow="create_alert", threshold="0.5000",
    )
    db_session.add_all([submitted, unbreached])
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        org_env["org"].id, submitted.id, Decimal("0.8100"), "api_report", None
    )
    assert db_session.execute(select(AIMonitoringBreachEvent)).scalars().all() == []


def test_a_different_metrics_tiers_are_not_dispatched(db_session, org_env):
    """Sibling lookup is scoped to (system, metric), not just the system."""
    submitted = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="default", order=0, workflow="create_alert", threshold="0.9500",
    )
    other_metric = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="critical", order=1, workflow="create_alert", threshold="0.9900",
        metric="output_drift",
    )
    db_session.add_all([submitted, other_metric])
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        org_env["org"].id, submitted.id, Decimal("0.8100"), "api_report", None
    )
    assert db_session.execute(select(AIMonitoringBreachEvent)).scalars().all() == []


def test_inactive_sibling_tier_is_ignored(db_session, org_env):
    submitted = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="default", order=0, workflow="create_alert", threshold="0.9500",
    )
    retired = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="critical", order=1, workflow="create_alert", threshold="0.9000",
    )
    retired.is_active = False
    db_session.add_all([submitted, retired])
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        org_env["org"].id, submitted.id, Decimal("0.8100"), "api_report", None
    )
    assert db_session.execute(select(AIMonitoringBreachEvent)).scalars().all() == []


# ================================================================ the route (item 2)


def _p4_key(db_session, org_id) -> str:
    return PatentScopedKeyService(db_session).provision_key(org_id, "p4_ingest", None)


def _push_body(system_id, **overrides):
    body = {
        "ai_system_id": str(system_id),
        "metric_type": "accuracy",
        "value": "0.8100",
        "collection_mode": "a",
        "sample_size": 500,
        "computed_by": "builtin-psi",
    }
    body.update(overrides)
    return body


def test_push_requires_a_p4_scoped_key(client, db_session, org_env):
    body = _push_body(org_env["system"].id)
    assert client.post(P4_PUSH, json=body).status_code == 401

    resp = client.post(P4_PUSH, json=body, headers={"Authorization": "Bearer not-a-real-key"})
    assert resp.status_code == 403


def test_a_p2_ingest_key_cannot_authenticate_the_p4_route(client, db_session, org_env):
    """The whole reason P4 got its own key type: cross-satellite key reuse must fail."""
    p2_key = PatentScopedKeyService(db_session).provision_key(org_env["org"].id, "ingest", None)
    db_session.commit()

    resp = client.post(
        P4_PUSH,
        json=_push_body(org_env["system"].id),
        headers={"Authorization": f"Bearer {p2_key}"},
    )
    assert resp.status_code == 403, "a P2 ingest key authenticated the P4 route"


def test_push_refuses_verdict_shaped_fields(client, db_session, org_env):
    key = _p4_key(db_session, org_env["org"].id)
    db_session.commit()

    for bad_field in ("is_breach", "severity", "within_threshold", "alert_level", "breached_at"):
        resp = client.post(
            P4_PUSH,
            json=_push_body(org_env["system"].id, **{bad_field: True}),
            headers={"Authorization": f"Bearer {key}"},
        )
        assert resp.status_code == 422, f"{bad_field} was accepted"
        assert "verdict-shaped" in resp.text, f"{bad_field} was rejected for the wrong reason"


def test_push_refuses_a_caller_supplied_reading_source(client, db_session, org_env):
    """reading_source is core's vocabulary. Letting a caller set it would let them
    mislabel an automated push as a human entry."""
    key = _p4_key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P4_PUSH,
        json=_push_body(org_env["system"].id, reading_source="manual"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 422


# ============================================================= END TO END (item 4)


def test_end_to_end_push_records_decides_audits_and_dispatches(client, db_session, org_env):
    """The full path P4 was built for, in one test.

    external push -> authenticated by a P4-scoped key -> reading persisted with
    provenance -> every configured tier evaluated -> breach decisions recorded and
    audited -> governance workflows dispatched and referenced back.
    """
    warning = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="warning", order=0, workflow="create_alert", threshold="0.9000",
    )
    critical = _config(
        org_env["org"].id, org_env["system"].id, org_env["user"].id,
        tier="critical", order=1, workflow="notify_oncall", threshold="0.8500",
    )
    db_session.add_all([warning, critical])
    key = _p4_key(db_session, org_env["org"].id)
    db_session.commit()

    response = client.post(
        P4_PUSH,
        json=_push_body(org_env["system"].id, value="0.8100"),
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["breach_events"] == 2
    assert payload["tiers_dispatched"] == ["warning", "critical"]
    # The response reports what core decided; it carries no verdict the satellite could
    # act on.
    assert "is_breach" not in response.text and "within_threshold" not in response.text

    # 1. the reading persisted, with its collection provenance
    reading = db_session.execute(
        select(AIMonitoringReading).where(AIMonitoringReading.id == uuid.UUID(payload["reading_id"]))
    ).scalars().one()
    assert reading.collection_mode == "a"
    assert reading.computed_by == "builtin-psi"
    assert reading.sample_size == 500
    assert reading.reading_source == "api_report", "core set this, not the caller"
    # No single-config verdict: the per-tier verdicts live in the breach events.
    assert reading.within_threshold is None

    # 2. one decision per breached tier, both frozen with their operands
    events = db_session.execute(
        select(AIMonitoringBreachEvent).where(AIMonitoringBreachEvent.reading_id == reading.id)
    ).scalars().all()
    assert {e.tier for e in events} == {"warning", "critical"}
    assert {e.threshold_value for e in events} == {Decimal("0.9000"), Decimal("0.8500")}
    assert all(e.observed_value == Decimal("0.8100") for e in events)

    # 3. every decision audited
    decided = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_env["org"].id,
            AuditLog.action == "ai_monitoring.breach_decided",
        )
    ).scalars().all()
    assert len(decided) == 2

    # 4. workflows dispatched and referenced back onto the decisions
    assert all(e.workflow_reference is not None for e in events)
    dispatched = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.breach_workflow_dispatched")
    ).scalars().all()
    assert len(dispatched) == 2

    alerts = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.organization_id == org_env["org"].id
        )
    ).scalars().all()
    assert {a.alert_type for a in alerts} == {"ai_monitoring", "ai_monitoring_oncall"}
    # The typed linkage back to the decision that caused each alert.
    for alert in alerts:
        assert alert.alert_context_json["breach_event_id"] in {str(e.id) for e in events}


def test_a_push_for_an_unconfigured_metric_is_still_stored(client, db_session, org_env):
    """A measurement is a fact even before anyone sets a threshold for it -- that is why
    ai_monitoring_readings.config_id became nullable."""
    key = _p4_key(db_session, org_env["org"].id)
    db_session.commit()

    response = client.post(
        P4_PUSH,
        json=_push_body(org_env["system"].id, metric_type="hallucination_rate"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["breach_events"] == 0
    assert body["tiers_dispatched"] == []

    reading = db_session.execute(
        select(AIMonitoringReading).where(AIMonitoringReading.id == uuid.UUID(body["reading_id"]))
    ).scalars().one()
    assert reading.config_id is None
    assert reading.metric_type == "hallucination_rate"


def test_push_is_scoped_to_the_key_issuing_organization(client, db_session, org_env):
    """The org comes from the key, never from a client header."""
    other_org = Organization(id=uuid.uuid4(), name="Other Org")
    db_session.add(other_org)
    db_session.flush()
    key = _p4_key(db_session, org_env["org"].id)
    db_session.commit()

    response = client.post(
        P4_PUSH,
        json=_push_body(org_env["system"].id),
        headers={"Authorization": f"Bearer {key}", "X-Organization-ID": str(other_org.id)},
    )
    assert response.status_code == 202
    assert response.json()["organization_id"] == str(org_env["org"].id)
