"""NULL `within_threshold` must never be read as a breach.

Migration 0321 relaxes `ai_monitoring_readings.within_threshold` and `config_id` to
NULLABLE so a measurement can exist without a single-config verdict (patent P4: a
tiered reading has one verdict per tier, in ai_monitoring_breach_events, and a lone
boolean cannot represent that).

The upstream P4 migration asserted that "neither relaxation changes an existing query's
result". That is false. It checked only the dashboard's SQL filter, which uses
`.is_(False)` and is NULL-safe, and missed three consumers:

  1. AIRecommendationEngine -- `not latest_reading.within_threshold`, where `not None`
     is True, inventing an "Active monitoring breach ... investigate immediately"
     recommendation for a reading nobody judged.
  2. AIMonitoringService.get_metric_history -- `sum(1 for r in readings if not
     r.within_threshold)`, inflating the dashboard's breach_count for the same reason.
  3. MonitoringReadingRead -- declared config_id and within_threshold non-optional, so
     serialising a NULL-bearing row raises ValidationError -> HTTP 500.

These tests construct NULL-bearing rows directly rather than through the API, because
the P4 ingest path that produces them is not wired yet.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.ai_governance.schemas.monitoring import MonitoringReadingRead
from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.ai_governance.services.ai_recommendation_engine import AIRecommendationEngine
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture()
def monitoring_fixture(db_session):
    """An org + AI system + one active config, with no readings yet."""
    org = Organization(id=uuid.uuid4(), name="NULL-verdict Org")
    user = User(
        id=uuid.uuid4(),
        email=f"null-verdict-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    system = AISystem(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Scoring Model",
        system_type="internal_model",
        lifecycle_status="production",
    )
    config = AIMonitoringConfig(
        id=uuid.uuid4(),
        organization_id=org.id,
        ai_system_id=system.id,
        metric_type="accuracy",
        threshold_value=Decimal("0.9000"),
        comparison_direction="below",
        alert_on_breach=True,
        is_active=True,
        created_by=user.id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add_all([org, user, system, config])
    db_session.flush()
    return {"org": org, "user": user, "system": system, "config": config}


def _reading(
    fixture,
    *,
    within_threshold: bool | None,
    config_id: uuid.UUID | None = ...,  # type: ignore[assignment]
    created_at: datetime | None = None,
) -> AIMonitoringReading:
    return AIMonitoringReading(
        id=uuid.uuid4(),
        organization_id=fixture["org"].id,
        config_id=fixture["config"].id if config_id is ... else config_id,
        value=Decimal("0.9500"),
        reading_source="api_report",
        within_threshold=within_threshold,
        created_at=created_at or datetime.now(UTC),
    )


def test_unjudged_reading_does_not_produce_a_breach_recommendation(db_session, monitoring_fixture):
    """A NULL verdict is 'nobody decided', not 'breached'.

    Fails before the fix: `not None` is True, so the engine emits a
    'monitoring_breach' recommendation for a reading that was never judged.
    """
    db_session.add(_reading(monitoring_fixture, within_threshold=None))
    db_session.flush()

    recommendations = AIRecommendationEngine().generate(
        monitoring_fixture["org"].id, monitoring_fixture["system"].id, db_session
    )

    breach_sources = [source for _text, source, _ref in recommendations if source == "monitoring_breach"]
    assert breach_sources == [], (
        "an unjudged reading (within_threshold IS NULL) was reported as an active "
        f"monitoring breach: {recommendations}"
    )


def test_genuine_breach_still_produces_a_recommendation(db_session, monitoring_fixture):
    """The NULL fix must not silence real breaches -- guards against over-correcting
    to `is True` on the wrong side of the comparison."""
    db_session.add(_reading(monitoring_fixture, within_threshold=False))
    db_session.flush()

    recommendations = AIRecommendationEngine().generate(
        monitoring_fixture["org"].id, monitoring_fixture["system"].id, db_session
    )

    breach_sources = [source for _text, source, _ref in recommendations if source == "monitoring_breach"]
    assert len(breach_sources) == 1, f"a real breach (within_threshold=False) was not reported: {recommendations}"


def test_within_threshold_reading_produces_no_recommendation(db_session, monitoring_fixture):
    db_session.add(_reading(monitoring_fixture, within_threshold=True))
    db_session.flush()

    recommendations = AIRecommendationEngine().generate(
        monitoring_fixture["org"].id, monitoring_fixture["system"].id, db_session
    )

    assert [s for _t, s, _r in recommendations if s == "monitoring_breach"] == []


def test_list_readings_breach_count_ignores_unjudged_readings(db_session, monitoring_fixture):
    """breach_count must count only decided breaches.

    Fails before the fix: `not r.within_threshold` counts every NULL, so a page of
    two unjudged readings and one real breach reports 3.
    """
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _reading(monitoring_fixture, within_threshold=None, created_at=now - timedelta(minutes=3)),
            _reading(monitoring_fixture, within_threshold=None, created_at=now - timedelta(minutes=2)),
            _reading(monitoring_fixture, within_threshold=False, created_at=now - timedelta(minutes=1)),
            _reading(monitoring_fixture, within_threshold=True, created_at=now),
        ]
    )
    db_session.flush()

    history = AIMonitoringService(db_session).list_readings(
        monitoring_fixture["org"].id,
        monitoring_fixture["config"].id,
    )

    breach_count = history["summary"]["breach_count_in_page"]
    assert breach_count == 1, (
        f"breach_count counted unjudged (NULL) readings as breaches: got "
        f"{breach_count}, expected 1"
    )


def test_read_schema_serialises_a_null_bearing_reading(db_session, monitoring_fixture):
    """Serialising an unjudged, config-less reading must not raise.

    Fails before the fix: MonitoringReadingRead declares config_id: uuid.UUID and
    within_threshold: bool, so pydantic raises ValidationError -> HTTP 500 on the
    readings-list and monitoring-dashboard endpoints.
    """
    row = _reading(monitoring_fixture, within_threshold=None, config_id=None)
    db_session.add(row)
    db_session.flush()

    try:
        serialised = MonitoringReadingRead.model_validate(row)
    except ValidationError as exc:  # pragma: no cover - this is the pre-fix path
        pytest.fail(f"MonitoringReadingRead rejected a NULL-bearing row: {exc}")

    assert serialised.config_id is None
    assert serialised.within_threshold is None
    assert serialised.value == Decimal("0.9500")
