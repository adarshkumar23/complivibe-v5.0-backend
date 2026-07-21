"""Characterization of Feature #66's single-config submit_reading path.

Written and passing against the pre-tiering implementation, BEFORE the governance
workflow engine was connected to this path, so it records what the live path actually
did rather than what anyone believed it did. It is not a wish-list: every assertion
below was observed green first.

Its job afterwards is to fail if connecting the engine changes any of it. Feature #66 is
live, customers have thresholds configured against it, and "the new engine also produces
an alert" is not the same claim as "the alert is identical".

The properties pinned here, in the order they matter:
  * exactly ONE ControlMonitoringAlert per breaching reading, of alert_type
    'ai_monitoring';
  * its severity comes from the METRIC (_severity_for_metric), not from a tier, and
    escalates on sustained degradation;
  * within_threshold is computed and stored by core;
  * no alert at all when the reading is healthy, or when alert_on_breach is false;
  * the config's last_checked_at / last_reading_value are updated either way.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture()
def f66(db_session):
    org = Organization(id=uuid.uuid4(), name="Feature 66 Org")
    user = User(
        id=uuid.uuid4(),
        email=f"f66-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    system = AISystem(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Legacy Monitored Model",
        system_type="internal_model",
        lifecycle_status="production",
    )
    db_session.add_all([org, user, system])
    db_session.flush()
    return {"org": org, "user": user, "system": system}


def _single_config(f66, *, metric="accuracy", direction="below", threshold="0.9000", alert_on_breach=True):
    """A config exactly as Feature #66 creates them: one per metric, default tier."""
    now = datetime.now(UTC)
    return AIMonitoringConfig(
        id=uuid.uuid4(),
        organization_id=f66["org"].id,
        ai_system_id=f66["system"].id,
        metric_type=metric,
        threshold_value=Decimal(threshold),
        comparison_direction=direction,
        alert_on_breach=alert_on_breach,
        is_active=True,
        created_by=f66["user"].id,
        created_at=now,
        updated_at=now,
        api_key_hash="k" * 64,
        # The values migration 0320's backfill assigns to every pre-P4 config.
        tier="default",
        escalation_order=0,
        threshold_operator="lte" if direction == "below" else "gte",
        workflow_to_trigger="create_alert",
    )


def _alerts(db_session, org_id):
    return db_session.execute(
        select(ControlMonitoringAlert).where(ControlMonitoringAlert.organization_id == org_id)
    ).scalars().all()


def test_breaching_reading_creates_exactly_one_alert(db_session, f66):
    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.8100"), "api_report", "evidently"
    )

    alerts = _alerts(db_session, f66["org"].id)
    assert len(alerts) == 1, "Feature #66 produces exactly one alert per breaching reading"
    assert alerts[0].alert_type == "ai_monitoring"
    assert alerts[0].status == "open"
    assert alerts[0].title == "AI monitoring breach: accuracy"


def test_alert_severity_comes_from_the_metric_not_a_tier(db_session, f66):
    """accuracy -> high, output_drift -> medium, everything else -> low.

    This is _severity_for_metric, and it is what a customer's existing alert routing is
    tuned against. A tier-derived severity would be a different number for the same
    reading.
    """
    cases = {"accuracy": "high", "output_drift": "medium", "response_time": "low"}
    for metric, expected in cases.items():
        cfg = _single_config(f66, metric=metric, direction="below", threshold="0.9000")
        db_session.add(cfg)
        db_session.flush()
        AIMonitoringService(db_session).submit_reading(
            f66["org"].id, cfg.id, Decimal("0.1000"), "api_report", None
        )
        alert = db_session.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.title == f"AI monitoring breach: {metric}"
            )
        ).scalars().one()
        assert alert.severity == expected, f"{metric} severity changed"


def test_within_threshold_is_computed_and_stored_by_core(db_session, f66):
    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()
    service = AIMonitoringService(db_session)

    breaching = service.submit_reading(f66["org"].id, config.id, Decimal("0.8100"), "api_report", None)
    healthy = service.submit_reading(f66["org"].id, config.id, Decimal("0.9500"), "api_report", None)

    assert breaching.within_threshold is False
    assert healthy.within_threshold is True
    # Not NULL: the single-config path still renders a verdict, which is what
    # Feature #66's dashboards read.
    assert breaching.within_threshold is not None


def test_healthy_reading_creates_no_alert(db_session, f66):
    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.9500"), "api_report", None
    )
    assert _alerts(db_session, f66["org"].id) == []


def test_alert_on_breach_false_suppresses_the_alert(db_session, f66):
    config = _single_config(f66, alert_on_breach=False)
    db_session.add(config)
    db_session.flush()

    reading = AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.8100"), "api_report", None
    )
    assert reading.within_threshold is False, "the breach is still recorded"
    assert _alerts(db_session, f66["org"].id) == [], "but alert_on_breach=False means no alert"


def test_sustained_degradation_escalates_severity(db_session, f66):
    """Several consecutive breaches escalate above the static per-metric severity.

    response_time is normally 'low'; a sustained run must raise it. This behaviour has
    no equivalent in the tier engine, which is why the legacy path is preserved rather
    than replaced.
    """
    config = _single_config(f66, metric="response_time", direction="above", threshold="1.0000")
    db_session.add(config)
    db_session.flush()
    service = AIMonitoringService(db_session)

    for _ in range(4):
        service.submit_reading(f66["org"].id, config.id, Decimal("5.0000"), "api_report", None)

    alerts = _alerts(db_session, f66["org"].id)
    assert len(alerts) == 4
    severities = [a.severity for a in alerts]
    assert "low" in severities, "the first breach is the static per-metric severity"
    assert any(s in {"high", "critical"} for s in severities), "a sustained run must escalate"
    escalated = [a for a in alerts if a.alert_context_json.get("sustained_degradation")]
    assert escalated, "sustained_degradation must be recorded in the alert context"


def test_alert_context_shape_is_unchanged(db_session, f66):
    """The exact keys a customer's tooling may already be reading."""
    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.8100"), "api_report", None
    )
    ctx = _alerts(db_session, f66["org"].id)[0].alert_context_json
    assert set(ctx) >= {
        "config_id",
        "ai_system_id",
        "metric_type",
        "value",
        "threshold_value",
        "comparison_direction",
        "breach_streak",
        "sustained_degradation",
        "pct_from_baseline",
    }


def test_config_tracking_fields_update_on_every_reading(db_session, f66):
    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()
    assert config.last_checked_at is None

    AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.9500"), "api_report", None
    )
    db_session.refresh(config)
    assert config.last_checked_at is not None
    assert config.last_reading_value == Decimal("0.9500")


def test_reading_source_is_still_validated(db_session, f66):
    from app.core.validation import InvalidChoiceError

    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()

    with pytest.raises(InvalidChoiceError):
        AIMonitoringService(db_session).submit_reading(
            f66["org"].id, config.id, Decimal("0.81"), "satellite_push", None
        )


def test_a_single_config_reading_records_no_breach_events(db_session, f66):
    """The pre-switch baseline for the tiering work.

    Feature #66 alone writes no ai_monitoring_breach_events rows. After the engine is
    connected this must STILL hold for a single-config reading -- otherwise the switch
    changed the single-tier case, which is exactly what must not happen.
    """
    from app.models.ai_monitoring_breach_event import AIMonitoringBreachEvent

    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.8100"), "api_report", None
    )

    events = db_session.execute(
        select(AIMonitoringBreachEvent).where(
            AIMonitoringBreachEvent.organization_id == f66["org"].id
        )
    ).scalars().all()
    assert events == [], "a lone Feature #66 config must not gain tiered breach events"


def test_readings_are_persisted_with_their_config(db_session, f66):
    config = _single_config(f66)
    db_session.add(config)
    db_session.flush()

    AIMonitoringService(db_session).submit_reading(
        f66["org"].id, config.id, Decimal("0.8100"), "api_report", "evidently"
    )
    rows = db_session.execute(
        select(AIMonitoringReading).where(AIMonitoringReading.config_id == config.id)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_tool == "evidently"
    assert rows[0].reading_source == "api_report"
