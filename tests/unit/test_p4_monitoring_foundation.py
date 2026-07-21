"""Step 7a: the P4 monitoring foundation -- registry export, breach audit, vocabularies.

Covers the pieces the nine-protocol governance engine will sit on top of, so that the
engine can be reviewed on its own terms later:

  * the threshold registry never serialises a credential, asserted against the schema's
    declared fields rather than by reading one happy-path response;
  * every breach decision writes an audit entry;
  * `suspend_system` is defined in the DB vocabulary but refused at dispatch;
  * collected readings always carry a valid `reading_source`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.validation import InvalidChoiceError

from app.ai_governance.schemas.monitoring import (
    REGISTRY_FORBIDDEN_FIELD_FRAGMENTS,
    ThresholdRegistryEntry,
    ThresholdRegistryRead,
)
from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.ai_governance.services.compliance_event_bridge import ComplianceEventBridge
from app.models.ai_monitoring_breach_event import AIMonitoringBreachEvent
from app.models.ai_monitoring_config import (
    DISABLED_WORKFLOW_VALUES,
    SELECTABLE_WORKFLOW_VALUES,
    WORKFLOW_VALUES,
    AIMonitoringConfig,
)
from app.models.ai_system import AISystem
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.user import User

KNOWN_API_KEY_HASH = "d41d8cd98f00b204e9800998ecf8427ed41d8cd98f00b204e9800998ecf8427e"


@pytest.fixture()
def p4_fixture(db_session):
    org = Organization(id=uuid.uuid4(), name="P4 Foundation Org")
    user = User(
        id=uuid.uuid4(),
        email=f"p4-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    system = AISystem(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Underwriting Model",
        system_type="internal_model",
        lifecycle_status="production",
    )
    now = datetime.now(UTC)
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
        created_at=now,
        updated_at=now,
        # The credential the registry must never emit.
        api_key_hash=KNOWN_API_KEY_HASH,
        tier="critical",
        escalation_order=1,
        threshold_operator="lte",
        workflow_to_trigger="create_alert",
    )
    db_session.add_all([org, user, system, config])
    db_session.flush()
    return {"org": org, "user": user, "system": system, "config": config}


# --------------------------------------------------------------- threshold registry


def test_registry_schema_declares_no_credential_shaped_field():
    """Schema-level, not convention-level.

    Inspects the DECLARED fields, so this fails when someone ADDS a credential field
    later -- which is the failure mode a happy-path response assertion cannot catch,
    because a response only shows what happens to be populated today.
    """
    for model in (ThresholdRegistryEntry, ThresholdRegistryRead):
        for field_name in model.model_fields:
            lowered = field_name.lower()
            for fragment in REGISTRY_FORBIDDEN_FIELD_FRAGMENTS:
                assert fragment not in lowered, (
                    f"{model.__name__}.{field_name} looks credential-shaped "
                    f"(matched '{fragment}'). The threshold registry is machine-facing; "
                    "a secret added here leaves core over the wire."
                )
    assert "api_key_hash" not in ThresholdRegistryEntry.model_fields


def test_registry_response_contains_neither_the_hash_field_nor_its_value(db_session, p4_fixture):
    """Round-trips a config holding a REAL api_key_hash and proves the value is absent
    from the serialised output -- not merely that the field name is missing."""
    payload = AIMonitoringService(db_session).build_threshold_registry(p4_fixture["org"].id)
    serialised = ThresholdRegistryRead.model_validate(payload).model_dump_json()

    assert KNOWN_API_KEY_HASH not in serialised, "the api_key_hash VALUE leaked into the registry"
    assert "api_key" not in serialised.lower()
    assert "hash" not in serialised.lower()


def test_registry_returns_the_threshold_a_collector_needs(db_session, p4_fixture):
    payload = AIMonitoringService(db_session).build_threshold_registry(p4_fixture["org"].id)
    registry = ThresholdRegistryRead.model_validate(payload)

    assert registry.total == 1
    entry = registry.thresholds[0]
    assert entry.config_id == p4_fixture["config"].id
    assert entry.metric_type == "accuracy"
    assert entry.tier == "critical"
    assert entry.threshold_operator == "lte"
    assert entry.threshold_value == Decimal("0.9000")
    assert entry.workflow_to_trigger == "create_alert"


def test_registry_excludes_inactive_and_deleted_configs(db_session, p4_fixture):
    p4_fixture["config"].is_active = False
    db_session.flush()

    payload = AIMonitoringService(db_session).build_threshold_registry(p4_fixture["org"].id)
    assert payload["total"] == 0


def test_registry_is_organization_scoped(db_session, p4_fixture):
    other_org = uuid.uuid4()
    payload = AIMonitoringService(db_session).build_threshold_registry(other_org)
    assert payload["total"] == 0


def test_registry_endpoint_requires_permission_and_hides_the_hash(client, db_session):
    from tests.helpers.auth_org import bootstrap_org_user

    ctx = bootstrap_org_user(client, email_prefix="registry")
    response = client.get(
        "/api/v1/ai-governance/monitoring/threshold-registry", headers=ctx["org_headers"]
    )
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()

    # Refused without credentials. 400 is core's own "missing X-Organization-ID"
    # response, which arrives before authentication -- the point being that no
    # threshold data is returned, not which 4xx it is.
    unauthenticated = client.get("/api/v1/ai-governance/monitoring/threshold-registry")
    assert unauthenticated.status_code >= 400
    assert "thresholds" not in unauthenticated.text


# ------------------------------------------------------------------ breach decisions


def _reading(bridge, fixture, *, mode="a"):
    return bridge.record_collected_reading(
        fixture["org"].id,
        value=Decimal("0.8100"),
        collection_mode=mode,
        config_id=fixture["config"].id,
        metric_type="accuracy",
        sample_size=250,
        computed_by="builtin-psi",
        reported_at=datetime.now(UTC),
    )


def test_every_breach_decision_writes_an_audit_entry(db_session, p4_fixture):
    bridge = ComplianceEventBridge(db_session)
    reading = _reading(bridge, p4_fixture)

    event = bridge.record_breach_decision(
        p4_fixture["org"].id,
        reading=reading,
        config=p4_fixture["config"],
        observed_value=Decimal("0.8100"),
    )

    logs = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == p4_fixture["org"].id,
            AuditLog.action == "ai_monitoring.breach_decided",
        )
    ).scalars().all()
    assert len(logs) == 1, "a breach decision was recorded without an audit entry"

    entry = logs[0]
    assert entry.entity_type == "ai_monitoring_breach_event"
    assert entry.entity_id == event.id
    # actor is None: core decided this, no human did. Recording a person would be a lie.
    assert entry.actor_user_id is None
    # Both operands present, so the decision is re-derivable from the trail alone even
    # if the config is edited afterwards.
    assert entry.after_json["observed_value"] == "0.8100"
    assert entry.after_json["threshold_value"] == "0.9000"
    assert entry.after_json["threshold_operator"] == "lte"
    assert entry.after_json["tier"] == "critical"


def test_breach_operands_are_frozen_against_later_config_edits(db_session, p4_fixture):
    bridge = ComplianceEventBridge(db_session)
    reading = _reading(bridge, p4_fixture)
    event = bridge.record_breach_decision(
        p4_fixture["org"].id,
        reading=reading,
        config=p4_fixture["config"],
        observed_value=Decimal("0.8100"),
    )

    p4_fixture["config"].threshold_value = Decimal("0.5000")
    p4_fixture["config"].tier = "warning"
    db_session.flush()
    db_session.refresh(event)

    assert event.threshold_value == Decimal("0.9000"), "editing the config rewrote history"
    assert event.tier == "critical"


def test_one_row_per_reading_and_tier(db_session, p4_fixture):
    from sqlalchemy.exc import IntegrityError

    bridge = ComplianceEventBridge(db_session)
    reading = _reading(bridge, p4_fixture)
    bridge.record_breach_decision(
        p4_fixture["org"].id,
        reading=reading,
        config=p4_fixture["config"],
        observed_value=Decimal("0.8100"),
    )
    with pytest.raises(IntegrityError):
        bridge.record_breach_decision(
            p4_fixture["org"].id,
            reading=reading,
            config=p4_fixture["config"],
            observed_value=Decimal("0.8100"),
        )


def test_workflow_reference_is_attached_and_separately_audited(db_session, p4_fixture):
    bridge = ComplianceEventBridge(db_session)
    reading = _reading(bridge, p4_fixture)
    event = bridge.record_breach_decision(
        p4_fixture["org"].id,
        reading=reading,
        config=p4_fixture["config"],
        observed_value=Decimal("0.8100"),
    )
    assert event.workflow_reference is None, "the reference must not be known before dispatch"

    bridge.attach_workflow_reference(event, "alert:1234", org_id=p4_fixture["org"].id)

    logs = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.breach_workflow_dispatched")
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].after_json["workflow_reference"] == "alert:1234"


# --------------------------------------------------------- suspend_system stays off


def test_suspend_system_is_defined_in_the_database_but_not_selectable():
    assert "suspend_system" in WORKFLOW_VALUES, "the column must still accept an existing value"
    assert "suspend_system" in DISABLED_WORKFLOW_VALUES
    assert "suspend_system" not in SELECTABLE_WORKFLOW_VALUES


def test_dispatch_refuses_suspend_system_rather_than_no_oping(db_session, p4_fixture):
    """The guard that matters: a config somehow holding suspend_system must fail loudly.

    Silently doing nothing is the dangerous outcome -- a customer who selected it
    believes their AI system is halted on breach.
    """
    bridge = ComplianceEventBridge(db_session)
    reading = _reading(bridge, p4_fixture)
    p4_fixture["config"].workflow_to_trigger = "suspend_system"
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        bridge.record_breach_decision(
            p4_fixture["org"].id,
            reading=reading,
            config=p4_fixture["config"],
            observed_value=Decimal("0.8100"),
        )
    assert exc.value.status_code == 422
    assert "not implemented" in exc.value.detail

    # And it left no half-written decision behind.
    events = db_session.execute(select(AIMonitoringBreachEvent)).scalars().all()
    assert events == []


def test_no_inbound_schema_offers_suspend_system():
    """Guards the other direction: if a create/update schema later exposes
    workflow_to_trigger, it must validate against the selectable set."""
    import app.ai_governance.schemas.monitoring as monitoring_schemas

    for name in dir(monitoring_schemas):
        model = getattr(monitoring_schemas, name)
        fields = getattr(model, "model_fields", None)
        if not isinstance(fields, dict) or "workflow_to_trigger" not in fields:
            continue
        if name.endswith("Read") or name.startswith("ThresholdRegistry"):
            continue  # read models reflect stored state, including legacy values
        field = fields["workflow_to_trigger"]
        rendered = str(field)
        assert "suspend_system" not in rendered, (
            f"{name}.workflow_to_trigger offers suspend_system, which has no implementation"
        )


# ------------------------------------------------------------------- reading_source


def test_collected_readings_always_carry_a_valid_reading_source(db_session, p4_fixture):
    bridge = ComplianceEventBridge(db_session)
    reading = _reading(bridge, p4_fixture)

    # NOT NULL with a CHECK constraint of ('manual', 'api_report') on the column.
    assert reading.reading_source == "api_report"
    assert reading.collection_mode == "a"
    # A collected measurement records what was measured, not what it meant.
    assert reading.within_threshold is None


def test_invalid_reading_source_is_a_422_not_a_500(db_session, p4_fixture):
    """Without validation this would reach the DB and violate the CHECK constraint,
    surfacing as an opaque 500 at insert time."""
    bridge = ComplianceEventBridge(db_session)
    # InvalidChoiceError, not HTTPException: core's own validate_choice idiom, turned
    # into a 422 by the global handler in app/main.py.
    with pytest.raises(InvalidChoiceError) as exc:
        bridge.record_collected_reading(
            p4_fixture["org"].id,
            value=Decimal("0.5"),
            collection_mode="a",
            reading_source="satellite_push",
        )
    assert exc.value.status_code == 422
    assert exc.value.field == "reading_source"
    assert exc.value.allowed == ["api_report", "manual"]


def test_invalid_collection_mode_is_rejected(db_session, p4_fixture):
    bridge = ComplianceEventBridge(db_session)
    with pytest.raises(InvalidChoiceError) as exc:
        bridge.record_collected_reading(
            p4_fixture["org"].id, value=Decimal("0.5"), collection_mode="z"
        )
    assert exc.value.status_code == 422
    assert exc.value.field == "collection_mode"


def test_a_collected_reading_may_have_no_config(db_session, p4_fixture):
    """Mode A/C collect metrics for a system before any threshold exists for them."""
    bridge = ComplianceEventBridge(db_session)
    reading = bridge.record_collected_reading(
        p4_fixture["org"].id,
        value=Decimal("0.4200"),
        collection_mode="c",
        metric_type="drift",
        computed_by="builtin-psi",
    )
    assert reading.config_id is None
    assert reading.within_threshold is None


# ------------------------------------------------- configurable P4 fields (7b)


def test_config_create_schema_accepts_the_p4_fields():
    from app.ai_governance.schemas.monitoring import MonitoringConfigCreate

    payload = MonitoringConfigCreate(
        metric_type="drift",
        threshold_value=Decimal("0.2"),
        comparison_direction="above",
        api_key="a-real-api-key-value",
        tier="critical",
        escalation_order=2,
        threshold_operator="gt",
        workflow_to_trigger="create_issue",
    )
    assert payload.tier == "critical"
    assert payload.workflow_to_trigger == "create_issue"


def test_config_create_schema_refuses_suspend_system():
    """The selectable set is enforced by the schema, not merely documented."""
    from pydantic import ValidationError as PydanticValidationError

    from app.ai_governance.schemas.monitoring import MonitoringConfigCreate

    with pytest.raises(PydanticValidationError):
        MonitoringConfigCreate(
            metric_type="accuracy",
            threshold_value=Decimal("0.9"),
            comparison_direction="below",
            api_key="a-real-api-key-value",
            workflow_to_trigger="suspend_system",
        )


def test_config_defaults_reproduce_pre_p4_behaviour(db_session, p4_fixture):
    """A client that knows nothing about tiers must get exactly what it got before."""
    from app.ai_governance.schemas.monitoring import MonitoringConfigCreate

    created = AIMonitoringService(db_session).create_config(
        p4_fixture["org"].id,
        p4_fixture["system"].id,
        MonitoringConfigCreate(
            metric_type="accuracy",
            threshold_value=Decimal("0.8"),
            comparison_direction="below",
            api_key="another-real-api-key",
        ),
        p4_fixture["user"].id,
    )
    assert created.tier == "default"
    assert created.escalation_order == 0
    assert created.workflow_to_trigger == "create_alert"
    # 'below' maps to 'lte' exactly, matching migration 0320's backfill and
    # check_threshold, so the comparison is unchanged.
    assert created.threshold_operator == "lte"


def test_p4_metric_types_are_now_accepted_by_the_service(db_session, p4_fixture):
    """ALLOWED_METRIC_TYPES was core's six; the DB accepts twenty-two since 0320."""
    from app.ai_governance.schemas.monitoring import MonitoringConfigCreate

    created = AIMonitoringService(db_session).create_config(
        p4_fixture["org"].id,
        p4_fixture["system"].id,
        MonitoringConfigCreate(
            metric_type="hallucination_rate",
            threshold_value=Decimal("0.05"),
            comparison_direction="above",
            api_key="yet-another-api-key",
            tier="warning",
        ),
        p4_fixture["user"].id,
    )
    assert created.metric_type == "hallucination_rate"
    assert created.threshold_operator == "gte"


def test_service_refuses_suspend_system_even_bypassing_the_schema(db_session, p4_fixture):
    """Server-side guard for internal callers that never touch the HTTP schema."""
    from types import SimpleNamespace

    payload = SimpleNamespace(
        model_dump=lambda: {
            "metric_type": "accuracy",
            "threshold_value": Decimal("0.9"),
            "comparison_direction": "below",
            "api_key": "an-api-key-value",
            "workflow_to_trigger": "suspend_system",
        }
    )
    with pytest.raises(InvalidChoiceError) as exc:
        AIMonitoringService(db_session).create_config(
            p4_fixture["org"].id, p4_fixture["system"].id, payload, p4_fixture["user"].id
        )
    assert exc.value.field == "workflow_to_trigger"
    assert "suspend_system" not in exc.value.allowed
