"""Interconnection Phase 1 -- Domain Event Bus core.

Covers the Step-2 additions to app/core/event_bus.py:
  * persist-on-publish: every emit() writes an immutable domain_events row,
    in the publisher's transaction, before dispatch, with correlation
    propagation across a cascade;
  * SAVEPOINT-per-handler failure isolation: a listener that raises -- including
    a DB error that would otherwise poison the shared Session -- never breaks the
    publisher's own work or any sibling listener, and is logged with context;
  * tenant scoping: a spoofed payload (org A claiming org B's entity) cannot
    read or mutate another organization's data.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.event_bus import EventBus, EventPayload, EventType
from app.core.startup import register_event_listeners
from app.models.audit_log import AuditLog
from app.models.domain_event import DomainEvent
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _reset_event_bus():
    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    yield
    bus.clear_listeners()


def _payload(db, *, org_id=None, event_type="test.custom", entity_type="control",
             entity_id=None, previous_value="a", new_value="b", triggered_by="user_action",
             triggered_by_user_id=None, correlation_id=None, payload=None):
    kwargs = dict(
        org_id=org_id or uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id or uuid.uuid4(),
        event_type=event_type,
        previous_value=previous_value,
        new_value=new_value,
        triggered_by=triggered_by,
        db=db,
    )
    if triggered_by_user_id is not None:
        kwargs["triggered_by_user_id"] = triggered_by_user_id
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id
    if payload is not None:
        kwargs["payload"] = payload
    return EventPayload(**kwargs)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_emit_persists_domain_event_row_with_all_fields(client, db_session):
    # a real org so the organization_id FK is satisfiable
    org = bootstrap_org_user(client, email_prefix="ebpersist")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    entity_id = uuid.uuid4()
    corr = uuid.uuid4()

    EventBus.get_instance().clear_listeners()  # no listeners -> isolate persistence
    EventBus.get_instance().emit(
        "test.persisted",
        _payload(db_session, org_id=org_id, event_type="test.persisted", entity_type="vendor",
                 entity_id=entity_id, previous_value="old", new_value="new",
                 triggered_by="user_action", triggered_by_user_id=user_id,
                 correlation_id=corr, payload={"k": "v"}),
    )
    db_session.commit()

    row = db_session.execute(
        select(DomainEvent).where(DomainEvent.organization_id == org_id, DomainEvent.event_type == "test.persisted")
    ).scalar_one()
    assert row.entity_type == "vendor"
    assert row.entity_id == entity_id
    assert row.previous_value == "old"
    assert row.new_value == "new"
    assert row.triggered_by == "user_action"
    assert row.triggered_by_user_id == user_id
    assert row.correlation_id == corr
    assert row.payload_json == {"k": "v"}
    assert row.occurred_at is not None


def test_emit_persists_before_dispatch_and_propagates_correlation_in_cascade(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ebcascade")
    org_id = uuid.UUID(org["organization_id"])
    corr = uuid.uuid4()
    bus = EventBus.get_instance()
    bus.clear_listeners()

    # a listener that re-emits a second event, propagating the correlation_id
    def cascader(p: EventPayload) -> None:
        bus.emit("test.child", _payload(p.db, org_id=p.org_id, event_type="test.child",
                                        entity_type="risk", correlation_id=p.correlation_id))

    bus.subscribe("test.parent", cascader)
    bus.emit("test.parent", _payload(db_session, org_id=org_id, event_type="test.parent", correlation_id=corr))
    db_session.commit()

    rows = db_session.execute(
        select(DomainEvent).where(DomainEvent.organization_id == org_id, DomainEvent.correlation_id == corr)
    ).scalars().all()
    types = sorted(r.event_type for r in rows)
    assert types == ["test.child", "test.parent"]  # both persisted, same correlation cascade


# --------------------------------------------------------------------------- #
# Failure isolation (the SAVEPOINT-per-handler fix)
# --------------------------------------------------------------------------- #
def test_throwing_listener_does_not_break_publisher_or_siblings(client, db_session, caplog):
    org = bootstrap_org_user(client, email_prefix="ebadv")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    entity_id = uuid.uuid4()
    bus = EventBus.get_instance()
    bus.clear_listeners()

    sibling_ran = {"value": False}

    # (bad) listener triggers a real DB error: an AuditLog with a NULL non-nullable
    # column. Without a per-handler SAVEPOINT this poisons the shared Session so
    # the sibling's subsequent flush would fail too.
    def bad_db_listener(p: EventPayload) -> None:
        p.db.add(AuditLog(organization_id=p.org_id, action=None, entity_type="x"))  # action NOT NULL
        p.db.flush()

    # (good) sibling writes a legitimate audit row and must succeed on a clean session
    def good_sibling(p: EventPayload) -> None:
        p.db.add(AuditLog(organization_id=p.org_id, actor_user_id=user_id,
                          action="sibling.ran", entity_type="control", entity_id=p.entity_id))
        p.db.flush()
        sibling_ran["value"] = True

    bus.subscribe("test.adv", bad_db_listener)
    bus.subscribe("test.adv", good_sibling)

    # publisher's OWN pre-emit work: a marker audit row that must survive
    db_session.add(AuditLog(organization_id=org_id, actor_user_id=user_id,
                            action="publisher.marker", entity_type="control", entity_id=entity_id))
    db_session.flush()

    with caplog.at_level("ERROR"):
        bus.emit("test.adv", _payload(db_session, org_id=org_id, event_type="test.adv",
                                      entity_id=entity_id, triggered_by_user_id=user_id))
    db_session.commit()  # publisher owns the commit; must succeed despite the bad handler

    actions = set(db_session.execute(
        select(AuditLog.action).where(AuditLog.organization_id == org_id)
    ).scalars().all())

    # (a) sibling still ran and its row committed
    assert sibling_ran["value"] is True
    assert "sibling.ran" in actions
    # (b) publisher's own DB work committed
    assert "publisher.marker" in actions
    # bad handler's row was rolled back to its savepoint -- not persisted
    # (c) the failure was logged with context
    assert "Event listener failed for event_type=test.adv" in caplog.text
    assert f"organization_id={org_id}" in caplog.text
    assert f"entity=control:{entity_id}" in caplog.text
    # (d) the domain_events row for the publish was still persisted (event not dropped)
    assert db_session.execute(
        select(DomainEvent).where(DomainEvent.organization_id == org_id, DomainEvent.event_type == "test.adv")
    ).scalar_one() is not None


def test_plain_exception_in_listener_is_isolated(client, db_session, caplog):
    org = bootstrap_org_user(client, email_prefix="ebplain")
    org_id = uuid.UUID(org["organization_id"])
    bus = EventBus.get_instance()
    bus.clear_listeners()
    order = []

    def boom(_p): order.append("boom"); raise RuntimeError("boom")
    def after(_p): order.append("after")

    bus.subscribe("test.plain", boom)
    bus.subscribe("test.plain", after)
    with caplog.at_level("ERROR"):
        bus.emit("test.plain", _payload(db_session, org_id=org_id, event_type="test.plain"))
    db_session.commit()

    assert order == ["boom", "after"]  # sibling after the raiser still ran
    assert "Event listener failed for event_type=test.plain" in caplog.text


# --------------------------------------------------------------------------- #
# Tenant scoping
# --------------------------------------------------------------------------- #
def test_spoofed_cross_tenant_event_cannot_mutate_other_orgs_data(client, db_session):
    # org B owns a risk+control; org A emits an event claiming org B's control_id.
    org_b = bootstrap_org_user(client, email_prefix="ebtenant-b")
    hb = org_b["org_headers"]
    risk_b = client.post("/api/v1/risks", headers=hb, json={
        "title": "org-b-risk", "category": "operational", "likelihood": 3, "impact": 3,
        "treatment_strategy": "mitigate"}).json()["id"]
    control_b = client.post("/api/v1/controls", headers=hb, json={
        "title": "org-b-control", "control_type": "process", "criticality": "high"}).json()["id"]
    client.post(f"/api/v1/risks/{risk_b}/controls", headers=hb, json={"control_id": control_b})
    # force a known inherent score for org B's risk
    rb = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_b))).scalar_one()
    rb.inherent_score = 1
    db_session.commit()

    org_a = bootstrap_org_user(client, email_prefix="ebtenant-a")
    org_a_id = uuid.UUID(org_a["organization_id"])

    # Spoof: org A's id, but org B's control entity_id. RiskRecalculationListener
    # filters strictly by payload.org_id, so it must find nothing to recalc.
    EventBus.get_instance().emit(
        EventType.CONTROL_STATUS_CHANGED,
        _payload(db_session, org_id=org_a_id, event_type=EventType.CONTROL_STATUS_CHANGED,
                 entity_type="control", entity_id=uuid.UUID(control_b),
                 previous_value="active", new_value="implemented", triggered_by="system"),
    )
    db_session.commit()

    rb_after = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_b))).scalar_one()
    assert rb_after.inherent_score == 1  # org B's data untouched by org A's spoofed event
