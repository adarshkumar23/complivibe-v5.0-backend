from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.compliance.services.risk_recalculation_listener import RiskRecalculationListener
from app.core.event_bus import EventBus, EventPayload, EventType
from app.core.startup import register_event_listeners
from app.models.audit_log import AuditLog
from app.models.evidence_item import EvidenceItem
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _reset_event_bus() -> None:
    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    yield
    bus.clear_listeners()


def _create_risk(client, headers: dict[str, str], title: str = "A15 Risk", likelihood: int = 3, impact: int = 3) -> str:
    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": title,
            "category": "operational",
            "likelihood": likelihood,
            "impact": impact,
            "treatment_strategy": "mitigate",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_control(client, headers: dict[str, str], title: str = "A15 Control") -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "control_type": "process",
            "criticality": "high",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _link_risk_control(client, headers: dict[str, str], risk_id: str, control_id: str) -> None:
    resp = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=headers,
        json={"control_id": control_id, "link_type": "mitigates"},
    )
    assert resp.status_code == 200


def _set_risk_score(db_session, risk_id: str, score: int) -> None:
    risk = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    risk.inherent_score = score
    db_session.commit()


def test_a15_event_bus_singleton_returns_same_instance():
    first = EventBus.get_instance()
    second = EventBus.get_instance()
    assert first is second


def test_a15_event_bus_subscribe_and_emit_calls_listener(db_session):
    bus = EventBus.get_instance()
    bus.clear_listeners()
    called: list[str] = []

    def listener(payload: EventPayload) -> None:
        called.append(str(payload.entity_id))

    bus.subscribe("custom.event", listener)
    bus.emit(
        "custom.event",
        EventPayload(
            org_id=uuid.uuid4(),
            entity_type="control",
            entity_id=uuid.uuid4(),
            event_type="custom.event",
            previous_value=None,
            new_value=None,
            triggered_by="system",
            db=db_session,
        ),
    )
    assert len(called) == 1


def test_a15_event_bus_listener_exception_is_swallowed_and_logged(db_session, caplog):
    bus = EventBus.get_instance()
    bus.clear_listeners()

    def bad_listener(_: EventPayload) -> None:
        raise RuntimeError("boom")

    bus.subscribe("bad.event", bad_listener)
    bus.emit(
        "bad.event",
        EventPayload(
            org_id=uuid.uuid4(),
            entity_type="control",
            entity_id=uuid.uuid4(),
            event_type="bad.event",
            previous_value=None,
            new_value=None,
            triggered_by="system",
            db=db_session,
        ),
    )
    assert "Event listener failed for event_type=bad.event" in caplog.text


def test_a15_event_bus_multiple_listeners_called_in_order(db_session):
    bus = EventBus.get_instance()
    bus.clear_listeners()
    order: list[str] = []

    def first(_: EventPayload) -> None:
        order.append("first")

    def second(_: EventPayload) -> None:
        order.append("second")

    bus.subscribe("ordered.event", first)
    bus.subscribe("ordered.event", second)
    bus.emit(
        "ordered.event",
        EventPayload(
            org_id=uuid.uuid4(),
            entity_type="control",
            entity_id=uuid.uuid4(),
            event_type="ordered.event",
            previous_value=None,
            new_value=None,
            triggered_by="system",
            db=db_session,
        ),
    )
    assert order == ["first", "second"]


def test_a15_event_bus_emit_unregistered_event_noop(db_session):
    bus = EventBus.get_instance()
    bus.clear_listeners()
    bus.emit(
        "does.not.exist",
        EventPayload(
            org_id=uuid.uuid4(),
            entity_type="control",
            entity_id=uuid.uuid4(),
            event_type="does.not.exist",
            previous_value=None,
            new_value=None,
            triggered_by="system",
            db=db_session,
        ),
    )


def test_a15_control_status_change_recalculates_linked_risks_and_writes_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-control")
    risk_id = _create_risk(client, org["org_headers"], likelihood=3, impact=3)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, score=1)

    patch = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=org["org_headers"],
        json={"status": "implemented"},
    )
    assert patch.status_code == 200

    risk = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    assert risk.inherent_score == 9

    log = db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "risk.score_recalculated",
            AuditLog.entity_id == risk.id,
        )
        .order_by(AuditLog.created_at.desc())
    ).scalars().first()
    assert log is not None
    assert log.metadata_json["context_json"]["triggered_by_event"] == EventType.CONTROL_STATUS_CHANGED


def test_a15_evidence_status_change_recalculates_linked_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-evidence-status")
    risk_id = _create_risk(client, org["org_headers"], likelihood=4, impact=3)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, score=1)

    ev = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "A15 Evidence", "evidence_type": "attestation"},
    )
    assert ev.status_code == 201
    evidence_id = ev.json()["id"]

    link = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=org["org_headers"],
        json={"control_id": control_id},
    )
    assert link.status_code == 200

    review = client.post(
        f"/api/v1/evidence/{evidence_id}/review",
        headers=org["org_headers"],
        json={"review_status": "verified"},
    )
    assert review.status_code == 200

    risk = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    assert risk.inherent_score == 12


def test_a15_vendor_score_update_recalculates_linked_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-vendor")
    risk_id = _create_risk(client, org["org_headers"], likelihood=5, impact=2)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, score=1)

    vendor = client.post(
        "/api/v1/compliance/vendors",
        headers=org["org_headers"],
        json={
            "name": "A15 Vendor",
            "vendor_type": "software",
            "owner_user_id": org["user_id"],
            "risk_tier": "high",
        },
    )
    assert vendor.status_code == 201
    vendor_id = vendor.json()["id"]

    vendor_link = client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control_id, "link_reason": "required"},
    )
    assert vendor_link.status_code == 201

    score_resp = client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/risk-scores",
        headers=org["org_headers"],
        json={"likelihood": "high", "impact": "high"},
    )
    assert score_resp.status_code == 201

    risk = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    assert risk.inherent_score == 10


def test_a15_recalculation_listener_no_linked_risks_no_writes(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-no-links")
    control_id = uuid.UUID(_create_control(client, org["org_headers"]))
    org_id = uuid.UUID(org["organization_id"])
    before_count = db_session.execute(
        select(AuditLog).where(AuditLog.organization_id == org_id, AuditLog.action == "risk.score_recalculated")
    ).scalars().all()

    RiskRecalculationListener().handle(
        EventPayload(
            org_id=org_id,
            entity_type="control",
            entity_id=control_id,
            event_type=EventType.CONTROL_STATUS_CHANGED,
            previous_value="not_started",
            new_value="implemented",
            triggered_by="user_action",
            db=db_session,
        )
    )

    after_count = db_session.execute(
        select(AuditLog).where(AuditLog.organization_id == org_id, AuditLog.action == "risk.score_recalculated")
    ).scalars().all()
    assert len(after_count) == len(before_count)


def test_a15_recalculation_listener_score_unchanged_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-unchanged")
    risk_id = _create_risk(client, org["org_headers"], likelihood=3, impact=3)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    org_id = uuid.UUID(org["organization_id"])

    RiskRecalculationListener().handle(
        EventPayload(
            org_id=org_id,
            entity_type="control",
            entity_id=uuid.UUID(control_id),
            event_type=EventType.CONTROL_STATUS_CHANGED,
            previous_value="not_started",
            new_value="implemented",
            triggered_by="user_action",
            db=db_session,
        )
    )

    recalcs = db_session.execute(
        select(AuditLog).where(AuditLog.organization_id == org_id, AuditLog.action == "risk.score_recalculated")
    ).scalars().all()
    assert len(recalcs) == 0


def test_a15_recalculation_listener_score_changed_audit_delta_context(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-changed")
    risk_id = _create_risk(client, org["org_headers"], likelihood=5, impact=5)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, score=3)
    org_id = uuid.UUID(org["organization_id"])

    RiskRecalculationListener().handle(
        EventPayload(
            org_id=org_id,
            entity_type="control",
            entity_id=uuid.UUID(control_id),
            event_type=EventType.CONTROL_STATUS_CHANGED,
            previous_value="not_started",
            new_value="implemented",
            triggered_by="user_action",
            db=db_session,
        )
    )

    log = db_session.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == org_id, AuditLog.action == "risk.score_recalculated")
        .order_by(AuditLog.created_at.desc())
    ).scalars().first()
    assert log is not None
    ctx = log.metadata_json["context_json"]
    assert ctx["previous_score"] == 3
    assert ctx["new_score"] == 25
    assert ctx["triggered_by_event"] == EventType.CONTROL_STATUS_CHANGED


def test_a15_risk_score_updated_event_emitted_when_score_changes(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-risk-updated-event")
    risk_id = _create_risk(client, org["org_headers"], likelihood=4, impact=4)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, score=2)

    captured: list[EventPayload] = []

    def collect(payload: EventPayload) -> None:
        captured.append(payload)

    bus = EventBus.get_instance()
    bus.subscribe(EventType.RISK_SCORE_UPDATED, collect)

    patch = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=org["org_headers"],
        json={"status": "in_progress"},
    )
    assert patch.status_code == 200
    assert len(captured) >= 1
    assert captured[0].event_type == EventType.RISK_SCORE_UPDATED


def test_a15_lazy_evidence_expiry_sets_expired_emits_and_recalculates(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a15-lazy-expiry")
    risk_id = _create_risk(client, org["org_headers"], likelihood=2, impact=4)
    control_id = _create_control(client, org["org_headers"])
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, score=1)

    ev = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "Expiring Evidence", "evidence_type": "attestation"},
    )
    assert ev.status_code == 201
    evidence_id = ev.json()["id"]
    link = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=org["org_headers"],
        json={"control_id": control_id},
    )
    assert link.status_code == 200

    evidence_row = db_session.execute(select(EvidenceItem).where(EvidenceItem.id == uuid.UUID(evidence_id))).scalar_one()
    evidence_row.valid_until = datetime.now(UTC) - timedelta(days=1)
    evidence_row.freshness_status = "fresh"
    db_session.commit()

    detail = client.get(f"/api/v1/evidence/{evidence_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["freshness_status"] == "expired"

    risk = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    assert risk.inherent_score == 8


def test_a15_register_event_listeners_registers_all_event_types():
    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    assert EventType.CONTROL_STATUS_CHANGED in bus._listeners
    assert EventType.EVIDENCE_STATUS_CHANGED in bus._listeners
    assert EventType.EVIDENCE_EXPIRED in bus._listeners
    assert EventType.VENDOR_SCORE_UPDATED in bus._listeners
    assert len(bus._listeners[EventType.CONTROL_STATUS_CHANGED]) >= 1


def test_a15_tenant_isolation_org_a_control_change_does_not_recompute_org_b(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a15-tenant-a")
    org_b = bootstrap_org_user(client, email_prefix="a15-tenant-b")

    risk_a = _create_risk(client, org_a["org_headers"], likelihood=4, impact=3)
    control_a = _create_control(client, org_a["org_headers"], title="A control")
    _link_risk_control(client, org_a["org_headers"], risk_a, control_a)
    _set_risk_score(db_session, risk_a, score=1)

    risk_b = _create_risk(client, org_b["org_headers"], likelihood=5, impact=5)
    control_b = _create_control(client, org_b["org_headers"], title="B control")
    _link_risk_control(client, org_b["org_headers"], risk_b, control_b)
    _set_risk_score(db_session, risk_b, score=2)

    patch = client.patch(
        f"/api/v1/controls/{control_a}",
        headers=org_a["org_headers"],
        json={"status": "implemented"},
    )
    assert patch.status_code == 200

    risk_a_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_a))).scalar_one()
    risk_b_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_b))).scalar_one()
    assert risk_a_row.inherent_score == 12
    assert risk_b_row.inherent_score == 2


def test_a15_clear_listeners_clears_registry():
    bus = EventBus.get_instance()
    bus.subscribe(EventType.CONTROL_STATUS_CHANGED, lambda _: None)
    assert bus._listeners
    bus.clear_listeners()
    assert bus._listeners == {}
