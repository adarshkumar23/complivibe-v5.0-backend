"""Interconnection Phase 1 -- Step 3 cross-cutting guarantees for the 4 migrated
listeners (DORA / vendor staleness / geopolitical / OT/ICS).

Per-connection byte-for-byte before/after equivalence is proven out-of-band by a
snapshot/sha256 harness; the permanent behavioral coverage lives in the original
per-feature test files (test_chain_dora_risk_register_crosscheck,
test_vendor_assessment_staleness_g8, test_geopolitical_risk_monitoring_t4_15,
test_ot_ics_convergence_t4_16), which pass unchanged after the migration.

This file adds the two cross-cutting checks the Step-3 brief requires:
  * tenant scoping -- a spoofed event (org A's id + org B's entity) cannot make a
    listener read or mutate org B's data (run against DORA + vendor staleness);
  * failure isolation -- a throwing sibling listener on a migrated event type does
    not block the real listener's work or the publisher's own commit (run against
    DORA).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.event_bus import EventBus, EventPayload, EventType
from app.core.startup import register_event_listeners
from app.models.dora_ict_register import DORAICTRegister
from app.models.risk import Risk
from app.models.vendor_assessment import VendorAssessment
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _reset_event_bus():
    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    yield
    bus.clear_listeners()


def _emit(db, *, event_type, org_id, entity_type, entity_id, payload):
    EventBus.get_instance().emit(
        event_type,
        EventPayload(
            org_id=org_id, entity_type=entity_type, entity_id=entity_id, event_type=event_type,
            previous_value=None, new_value=None, triggered_by="system", db=db, payload=payload,
        ),
    )


def _risk_count(db, org_id) -> int:
    return len(db.execute(select(Risk).where(Risk.organization_id == org_id)).scalars().all())


# --------------------------------------------------------------------------- #
# Tenant scoping -- DORA
# --------------------------------------------------------------------------- #
def test_dora_listener_spoofed_cross_tenant_event_cannot_touch_other_org(client, db_session):
    org_b = bootstrap_org_user(client, email_prefix="s3-dora-b")
    # Create a NON-gap entry in org B (no cascade, risk_id stays None), then flip it
    # into a gap state directly in the DB without going through the trigger.
    entry = client.post("/api/v1/compliance/dora/ict-register", headers=org_b["org_headers"], json={
        "counterparty_name": "VictimCorp", "service_description": "svc",
        "is_critical_function": False, "sub_outsourcing_used": False,
        "exit_strategy_documented": False, "owner_id": org_b["user_id"], "status": "active"}).json()
    assert entry["risk_id"] is None
    row = db_session.execute(select(DORAICTRegister).where(DORAICTRegister.id == uuid.UUID(entry["id"]))).scalar_one()
    row.is_critical_function = True  # now it IS a gap (critical + no exit strategy), risk_id still None
    db_session.commit()

    org_a = bootstrap_org_user(client, email_prefix="s3-dora-a")
    org_a_id = uuid.UUID(org_a["organization_id"])
    org_b_id = uuid.UUID(org_b["organization_id"])
    before_b = _risk_count(db_session, org_b_id)

    # Spoof: org A's id, org B's entry id.
    _emit(db_session, event_type=EventType.DORA_REGISTER_GAP_DETECTED, org_id=org_a_id,
          entity_type="dora_ict_register", entity_id=row.id, payload={"reason": "missing_exit_strategy"})
    db_session.commit()

    db_session.refresh(row)
    assert row.risk_id is None                          # org B's entry untouched
    assert _risk_count(db_session, org_b_id) == before_b  # no risk created in org B
    assert _risk_count(db_session, org_a_id) == 0         # nor in the spoofing org

    # Positive control: the CORRECT org-scoped event does create the risk.
    _emit(db_session, event_type=EventType.DORA_REGISTER_GAP_DETECTED, org_id=org_b_id,
          entity_type="dora_ict_register", entity_id=row.id, payload={"reason": "missing_exit_strategy"})
    db_session.commit()
    db_session.refresh(row)
    assert row.risk_id is not None
    assert _risk_count(db_session, org_b_id) == before_b + 1


# --------------------------------------------------------------------------- #
# Tenant scoping -- vendor staleness
# --------------------------------------------------------------------------- #
def test_vendor_staleness_listener_spoofed_cross_tenant_event_cannot_touch_other_org(client, db_session):
    org_b = bootstrap_org_user(client, email_prefix="s3-vstale-b")
    hb = org_b["org_headers"]
    vendor = client.post("/api/v1/compliance/vendors", headers=hb, json={
        "name": "VictimVendor", "vendor_type": "software", "owner_user_id": org_b["user_id"]}).json()
    # Future due date -> not overdue -> no cascade, risk_id None. Then backdate in DB.
    future = (date.today() + timedelta(days=30)).isoformat()
    assessment = client.post(f"/api/v1/compliance/vendors/{vendor['id']}/assessments", headers=hb, json={
        "title": "Review", "assessment_type": "periodic", "due_date": future}).json()
    assert assessment["risk_id"] is None
    row = db_session.execute(select(VendorAssessment).where(VendorAssessment.id == uuid.UUID(assessment["id"]))).scalar_one()
    row.due_date = date.today() - timedelta(days=400)  # now overdue, risk_id still None
    db_session.commit()

    org_a = bootstrap_org_user(client, email_prefix="s3-vstale-a")
    org_a_id = uuid.UUID(org_a["organization_id"])
    org_b_id = uuid.UUID(org_b["organization_id"])
    before_b = _risk_count(db_session, org_b_id)

    _emit(db_session, event_type=EventType.VENDOR_ASSESSMENT_STALE, org_id=org_a_id,
          entity_type="vendor_assessment", entity_id=row.id,
          payload={"reason": "assessment_overdue", "vendor_id": str(vendor["id"])})
    db_session.commit()

    db_session.refresh(row)
    assert row.risk_id is None
    assert _risk_count(db_session, org_b_id) == before_b
    assert _risk_count(db_session, org_a_id) == 0

    # Positive control
    _emit(db_session, event_type=EventType.VENDOR_ASSESSMENT_STALE, org_id=org_b_id,
          entity_type="vendor_assessment", entity_id=row.id,
          payload={"reason": "assessment_overdue", "vendor_id": str(vendor["id"])})
    db_session.commit()
    db_session.refresh(row)
    assert row.risk_id is not None
    assert _risk_count(db_session, org_b_id) == before_b + 1


# --------------------------------------------------------------------------- #
# Failure isolation -- DORA (a throwing sibling must not block the real listener
# or the publisher's commit)
# --------------------------------------------------------------------------- #
def test_throwing_sibling_does_not_block_migrated_listener_or_publisher_commit(client, db_session, caplog):
    org = bootstrap_org_user(client, email_prefix="s3-fail")
    org_id = uuid.UUID(org["organization_id"])
    bus = EventBus.get_instance()

    def bad_sibling(_p: EventPayload) -> None:
        raise RuntimeError("sibling boom")

    # Register the bad sibling on the same event type as the real DORA listener.
    bus.subscribe(EventType.DORA_REGISTER_GAP_DETECTED, bad_sibling)

    with caplog.at_level("ERROR"):
        resp = client.post("/api/v1/compliance/dora/ict-register", headers=org["org_headers"], json={
            "counterparty_name": "ResilientCorp", "service_description": "svc",
            "is_critical_function": True, "sub_outsourcing_used": False,
            "exit_strategy_documented": False, "owner_id": org["user_id"], "status": "active"})

    # (publisher's own commit succeeded: the DORA entry was created and returned)
    assert resp.status_code == 201, resp.text
    entry = resp.json()
    # (the real DORARiskRegisterListener still ran despite the throwing sibling)
    assert entry["risk_id"] is not None
    # (and the failure was logged)
    assert "Event listener failed for event_type=dora.register_gap_detected" in caplog.text
    # the linked risk is a real committed row
    risk = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(entry["risk_id"]))).scalar_one_or_none()
    assert risk is not None
