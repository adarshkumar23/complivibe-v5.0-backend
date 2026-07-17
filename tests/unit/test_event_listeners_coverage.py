"""Direct per-listener unit coverage for every event-bus listener.

The existing Phase-1 files (test_event_bus_domain_events_phase1,
test_event_bus_step3_migrated_listeners_phase1) prove the *bus contract* --
persist-on-publish, SAVEPOINT isolation, tenant scoping -- driven end-to-end
through publisher endpoints. This file is complementary: for EACH listener it
(1) constructs an EventPayload and calls ``listener.handle(payload)`` DIRECTLY,
asserting the real row/side-effect it writes lands in db_session, and (2) calls
``listener.register(bus)`` on a fresh EventBus and asserts it subscribed to the
expected EventType(s). Nothing here re-proves the cross-cutting bus guarantees.

Listeners covered (8):
  * EvidenceAssessmentCandidateListener   -> writes evidence_ai_assessment_candidates
  * CompoundPatternCandidateListener      -> writes compound_insight_candidates
  * EntityScoreInvalidationListener       -> recomputes -> new entity_risk_scores row
  * RiskRecalculationListener             -> mutates risk score + risk.score_recalculated audit
  * DORARiskRegisterListener              -> Risk + ControlMonitoringAlert + Issue + audit
  * VendorStalenessListener               -> Risk + ControlMonitoringAlert + audit
  * GeopoliticalVendorRiskListener        -> Risk + exposure.cascaded_risk_id
  * OtIcsRiskRegisterListener             -> Risk + finding.risk_id
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.compliance.services.compound_pattern_candidate_listener import (
    _SUBSCRIBED as _COMPOUND_SUBSCRIBED,
    CompoundPatternCandidateListener,
)
from app.compliance.services.dora_risk_register_listener import DORARiskRegisterListener
from app.compliance.services.entity_score_invalidation_listener import EntityScoreInvalidationListener
from app.compliance.services.evidence_assessment_candidate_listener import EvidenceAssessmentCandidateListener
from app.compliance.services.geopolitical_vendor_risk_listener import GeopoliticalVendorRiskListener
from app.compliance.services.ot_ics_risk_register_listener import OtIcsRiskRegisterListener
from app.compliance.services.risk_recalculation_listener import RiskRecalculationListener
from app.compliance.services.vendor_staleness_listener import VendorStalenessListener
from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.compound_insight import CompoundInsightCandidate
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.entity_risk_score import EntityRiskScore
from app.models.evidence_ai_assessment import EvidenceAiAssessmentCandidate
from app.models.geopolitical_risk_signal import GeopoliticalRiskSignal
from app.models.issue import Issue
from app.models.ot_ics_asset import OtIcsAsset
from app.models.ot_ics_finding import OtIcsFinding
from app.models.risk import Risk
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_geopolitical_exposure import VendorGeopoliticalExposure
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _isolate_singleton_bus():
    """Direct handle() calls must be isolated: some handlers (e.g. risk
    recalculation, or RiskService.create_risk_from_service) may emit on the
    global singleton bus. With no listeners registered those emits are
    harmless persist-only no-ops, keeping each direct test deterministic. The
    register() assertions use their OWN fresh EventBus, never the singleton.
    """
    bus = EventBus.get_instance()
    bus.clear_listeners()
    yield
    bus.clear_listeners()


def _payload(db, *, org_id, entity_type, entity_id, event_type,
             triggered_by_user_id=None, payload=None):
    return EventPayload(
        org_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        previous_value=None,
        new_value=None,
        triggered_by="system",
        db=db,
        triggered_by_user_id=triggered_by_user_id,
        payload=payload or {},
    )


def _subscribed_event_types(listener) -> set[str]:
    """register() on a throwaway bus, return the set of subscribed event types
    whose listener list contains this listener's bound handle."""
    bus = EventBus()
    listener.register(bus)
    return {
        et for et, listeners in bus._listeners.items()
        if any(l == listener.handle for l in listeners)
    }


# --------------------------------------------------------------------------- #
# 1. EvidenceAssessmentCandidateListener (flush-only flag writer)
# --------------------------------------------------------------------------- #
def test_evidence_assessment_candidate_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-evid")
    org_id = uuid.UUID(org["organization_id"])
    evidence_id = uuid.uuid4()

    listener = EvidenceAssessmentCandidateListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="evidence_item",
        entity_id=evidence_id, event_type=EventType.EVIDENCE_UPLOADED,
    ))

    row = db_session.execute(
        select(EvidenceAiAssessmentCandidate).where(
            EvidenceAiAssessmentCandidate.organization_id == org_id,
            EvidenceAiAssessmentCandidate.evidence_item_id == evidence_id,
        )
    ).scalar_one()
    assert row.event_type == EventType.EVIDENCE_UPLOADED
    assert row.processed_at is None  # queued, not yet drained

    assert _subscribed_event_types(listener) == {EventType.EVIDENCE_UPLOADED}


# --------------------------------------------------------------------------- #
# 2. CompoundPatternCandidateListener (flush-only flag writer)
# --------------------------------------------------------------------------- #
def test_compound_pattern_candidate_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-compound")
    org_id = uuid.UUID(org["organization_id"])
    node_id = uuid.uuid4()

    listener = CompoundPatternCandidateListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="risk", entity_id=node_id,
        event_type=EventType.RISK_SCORE_UPDATED,
    ))

    row = db_session.execute(
        select(CompoundInsightCandidate).where(
            CompoundInsightCandidate.organization_id == org_id,
            CompoundInsightCandidate.entity_id == node_id,
        )
    ).scalar_one()
    assert row.entity_type == "risk"
    assert row.event_type == EventType.RISK_SCORE_UPDATED
    assert row.processed_at is None

    assert _subscribed_event_types(listener) == set(_COMPOUND_SUBSCRIBED)


# --------------------------------------------------------------------------- #
# 3. EntityScoreInvalidationListener (recompute cascade)
# --------------------------------------------------------------------------- #
def test_entity_score_invalidation_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-entity")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    # A business unit + a risk linked to it -> a recomputable entity.
    bu = BusinessUnit(organization_id=org_id, name="Payments", code="PAY", created_by=user_id)
    db_session.add(bu)
    db_session.flush()

    risk_id = uuid.UUID(client.post("/api/v1/risks", headers=org["org_headers"], json={
        "title": "entity-linked-risk", "category": "operational",
        "likelihood": 4, "impact": 4, "treatment_strategy": "mitigate",
    }).json()["id"])
    risk = db_session.execute(select(Risk).where(Risk.id == risk_id)).scalar_one()
    risk.business_unit_id = bu.id
    db_session.flush()

    # A stored score snapshot whose component set INCLUDES this risk id -- this is
    # what makes the listener consider the BU an invalidation target.
    snapshot = EntityRiskScore(
        organization_id=org_id, entity_type="business_unit", entity_id=bu.id,
        entity_label="Payments", composite_score=10, score_band="low", risk_count=1,
        score_method="equal_weight",
        component_risks_json=[{"risk_id": str(risk_id), "risk_name": "entity-linked-risk", "score": 5}],
        computed_at=datetime.now(UTC),
    )
    db_session.add(snapshot)
    db_session.flush()

    before = db_session.execute(
        select(func.count()).select_from(EntityRiskScore).where(
            EntityRiskScore.organization_id == org_id, EntityRiskScore.entity_id == bu.id,
        )
    ).scalar_one()

    listener = EntityScoreInvalidationListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="risk", entity_id=risk_id,
        event_type=EventType.RISK_SCORE_UPDATED,
    ))

    after = db_session.execute(
        select(func.count()).select_from(EntityRiskScore).where(
            EntityRiskScore.organization_id == org_id, EntityRiskScore.entity_id == bu.id,
        )
    ).scalar_one()
    assert after == before + 1  # a fresh recomputed score row was written for the BU

    assert _subscribed_event_types(listener) == {EventType.RISK_SCORE_UPDATED}


# --------------------------------------------------------------------------- #
# 4. RiskRecalculationListener (score mutation on linked-control change)
# --------------------------------------------------------------------------- #
def test_risk_recalculation_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-riskrecalc")
    h = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])

    risk_id = uuid.UUID(client.post("/api/v1/risks", headers=h, json={
        "title": "recalc-risk", "category": "operational",
        "likelihood": 3, "impact": 3, "treatment_strategy": "mitigate",
    }).json()["id"])
    control_id = uuid.UUID(client.post("/api/v1/controls", headers=h, json={
        "title": "recalc-control", "control_type": "process", "criticality": "high",
    }).json()["id"])
    client.post(f"/api/v1/risks/{risk_id}/controls", headers=h, json={"control_id": str(control_id)})

    # Poison the stored inherent_score so a recompute is guaranteed to differ.
    risk = db_session.execute(select(Risk).where(Risk.id == risk_id)).scalar_one()
    risk.inherent_score = 1
    db_session.commit()

    listener = RiskRecalculationListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="control", entity_id=control_id,
        event_type=EventType.CONTROL_STATUS_CHANGED,
    ))

    db_session.refresh(risk)
    assert risk.inherent_score != 1  # recomputed to the correct value

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "risk.score_recalculated",
            AuditLog.entity_id == risk_id,
        )
    ).scalar_one()
    assert audit is not None

    assert _subscribed_event_types(listener) == {
        EventType.CONTROL_STATUS_CHANGED, EventType.EVIDENCE_STATUS_CHANGED,
        EventType.EVIDENCE_EXPIRED, EventType.VENDOR_SCORE_UPDATED,
    }


# --------------------------------------------------------------------------- #
# 5. DORARiskRegisterListener (Risk + alert + issue + audit)
# --------------------------------------------------------------------------- #
def test_dora_risk_register_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-dora")
    h = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])

    # Non-gap entry -> API does NOT cascade, risk_id stays None so the listener
    # can create the linkage itself when we emit the gap event directly.
    entry_id = uuid.UUID(client.post("/api/v1/compliance/dora/ict-register", headers=h, json={
        "counterparty_name": "CriticalCloudCo", "service_description": "hosting",
        "is_critical_function": False, "sub_outsourcing_used": False,
        "exit_strategy_documented": False, "owner_id": org["user_id"], "status": "active",
    }).json()["id"])

    listener = DORARiskRegisterListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="dora_ict_register", entity_id=entry_id,
        event_type=EventType.DORA_REGISTER_GAP_DETECTED,
        payload={"reason": "missing_exit_strategy"},
    ))

    from app.models.dora_ict_register import DORAICTRegister
    row = db_session.execute(select(DORAICTRegister).where(DORAICTRegister.id == entry_id)).scalar_one()
    assert row.risk_id is not None
    risk = db_session.execute(select(Risk).where(Risk.id == row.risk_id)).scalar_one()
    assert risk.organization_id == org_id

    alert = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.organization_id == org_id,
            ControlMonitoringAlert.alert_type == "dora_ict_register_gap",
        )
    ).scalar_one()
    assert alert.status == "open"

    issue = db_session.execute(
        select(Issue).where(
            Issue.organization_id == org_id,
            Issue.source_type == "risk_assessment",
            Issue.source_id == entry_id,
        )
    ).scalar_one()
    assert issue is not None

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "dora.ict_entry_risk_linked",
        )
    ).scalar_one()
    assert audit is not None

    assert _subscribed_event_types(listener) == {EventType.DORA_REGISTER_GAP_DETECTED}


# --------------------------------------------------------------------------- #
# 6. VendorStalenessListener (Risk + alert + audit)
# --------------------------------------------------------------------------- #
def test_vendor_staleness_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-vstale")
    h = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])

    vendor_id = uuid.UUID(client.post("/api/v1/compliance/vendors", headers=h, json={
        "name": "StaleVendor", "vendor_type": "software", "owner_user_id": org["user_id"],
    }).json()["id"])
    # Future due date -> not overdue -> API does not cascade, risk_id None.
    future = (date.today() + timedelta(days=30)).isoformat()
    assessment_id = uuid.UUID(client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/assessments", headers=h, json={
            "title": "Annual review", "assessment_type": "periodic", "due_date": future,
        }).json()["id"])
    # Backdate so it is genuinely overdue when the listener reasons about it.
    assessment = db_session.execute(
        select(VendorAssessment).where(VendorAssessment.id == assessment_id)
    ).scalar_one()
    assessment.due_date = date.today() - timedelta(days=90)
    db_session.commit()

    listener = VendorStalenessListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="vendor_assessment", entity_id=assessment_id,
        event_type=EventType.VENDOR_ASSESSMENT_STALE,
        payload={"reason": "assessment_overdue", "vendor_id": str(vendor_id)},
    ))

    db_session.refresh(assessment)
    assert assessment.risk_id is not None
    risk = db_session.execute(select(Risk).where(Risk.id == assessment.risk_id)).scalar_one()
    assert risk.organization_id == org_id

    alert = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.organization_id == org_id,
            ControlMonitoringAlert.alert_type == "vendor_assessment_overdue",
        )
    ).scalar_one()
    assert alert.status == "open"

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "vendor_assessment.risk_linked",
        )
    ).scalar_one()
    assert audit is not None

    assert _subscribed_event_types(listener) == {EventType.VENDOR_ASSESSMENT_STALE}


# --------------------------------------------------------------------------- #
# 7. GeopoliticalVendorRiskListener (Risk + exposure.cascaded_risk_id)
# --------------------------------------------------------------------------- #
def test_geopolitical_vendor_risk_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-geo")
    h = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])
    region = "Eastern Europe"

    vendor_id = uuid.UUID(client.post("/api/v1/compliance/vendors", headers=h, json={
        "name": "RegionVendor", "vendor_type": "software", "owner_user_id": org["user_id"],
    }).json()["id"])

    exposure = VendorGeopoliticalExposure(
        organization_id=org_id, vendor_id=vendor_id, region=region, is_primary=True,
    )
    signal = GeopoliticalRiskSignal(
        organization_id=org_id, region=region, category="conflict", severity="critical",
        source="gdelt", headline="Escalating conflict in region", detected_at=datetime.now(UTC),
    )
    db_session.add_all([exposure, signal])
    db_session.flush()

    listener = GeopoliticalVendorRiskListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="geopolitical_risk_signal", entity_id=signal.id,
        event_type=EventType.GEOPOLITICAL_SIGNAL_CRITICAL, payload={"region": region},
    ))

    db_session.refresh(exposure)
    assert exposure.cascaded_risk_id is not None
    risk = db_session.execute(select(Risk).where(Risk.id == exposure.cascaded_risk_id)).scalar_one()
    assert risk.organization_id == org_id
    assert risk.category == "vendor"

    assert _subscribed_event_types(listener) == {EventType.GEOPOLITICAL_SIGNAL_CRITICAL}


# --------------------------------------------------------------------------- #
# 8. OtIcsRiskRegisterListener (Risk + finding.risk_id)
# --------------------------------------------------------------------------- #
def test_ot_ics_risk_register_listener(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lst-otics")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    asset = OtIcsAsset(
        organization_id=org_id, name="PLC-1", asset_type="plc",
        network_segment="segment-a", criticality="high", status="active", created_by=user_id,
    )
    db_session.add(asset)
    db_session.flush()
    finding = OtIcsFinding(
        organization_id=org_id, asset_id=asset.id, finding_type="default_credentials",
        severity="critical", description="Default admin creds in use", detected_at=datetime.now(UTC),
    )
    db_session.add(finding)
    db_session.flush()

    listener = OtIcsRiskRegisterListener()
    listener.handle(_payload(
        db_session, org_id=org_id, entity_type="ot_ics_finding", entity_id=finding.id,
        event_type=EventType.OT_ICS_FINDING_INGESTED,
    ))

    db_session.refresh(finding)
    assert finding.risk_id is not None
    risk = db_session.execute(select(Risk).where(Risk.id == finding.risk_id)).scalar_one()
    assert risk.organization_id == org_id
    assert risk.category == "operational"

    assert _subscribed_event_types(listener) == {EventType.OT_ICS_FINDING_INGESTED}
