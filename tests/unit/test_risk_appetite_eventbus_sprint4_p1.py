from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.ai_governance.services.mlops_adapter_service import MLopsAdapterService
from app.compliance.services.audit_finding_service import AuditFindingService
from app.compliance.services.compliance_risk_recommendation_service import ComplianceRiskRecommendationService
from app.core.event_bus import EventBus
from app.core.startup import register_event_listeners
from app.models.ai_system import AISystem
from app.models.audit_engagement import AuditEngagement
from app.models.compliance_risk_recommendation import ComplianceRiskRecommendation
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.mlflow_connection import MLflowConnection
from app.models.risk import Risk
from app.models.risk_appetite_threshold import RiskAppetiteThreshold
from app.models.vendor_risk_score import VendorRiskScore
from app.services.control_service import ControlService
from app.services.evidence_service import EvidenceService
from app.services.vendor_risk_service import VendorRiskService
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _reset_event_bus() -> None:
    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    yield
    bus.clear_listeners()


def _create_threshold(db_session, org_id: str, user_id: str, *, max_score: int, category: str = "operational") -> None:
    row = RiskAppetiteThreshold(
        organization_id=uuid.UUID(org_id),
        scope_type="org",
        scope_id=None,
        risk_category=category,
        max_acceptable_score=max_score,
        escalation_owner_id=uuid.UUID(user_id),
        is_active=True,
        created_by_user_id=uuid.UUID(user_id),
    )
    db_session.add(row)
    db_session.commit()


def _create_risk(client, headers: dict[str, str], *, title: str, likelihood: int, impact: int) -> str:
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


def _create_control(client, headers: dict[str, str], *, title: str) -> str:
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
    row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    row.inherent_score = score
    db_session.commit()


def _alert_for_risk(db_session, org_id: str, risk_id: uuid.UUID) -> ControlMonitoringAlert | None:
    rows = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.organization_id == uuid.UUID(org_id),
            ControlMonitoringAlert.alert_type == "risk_threshold_breach",
            ControlMonitoringAlert.status == "open",
        )
    ).scalars().all()
    for row in rows:
        ctx = row.alert_context_json if isinstance(row.alert_context_json, dict) else {}
        if str(ctx.get("risk_id")) == str(risk_id):
            return row
    return None


def test_s4_p1_appetite_check_mlops_auto_risk_creates_breach_alert(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p1-mlops")
    # MLOps-adapter auto-created risks are categorized "ai_governance" (see
    # app/ai_governance/services/mlops_adapter_service.py); the threshold must match
    # that category for the breach check to resolve to it.
    _create_threshold(db_session, org["organization_id"], org["user_id"], max_score=5, category="ai_governance")

    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    ai_system = AISystem(
        organization_id=org_id,
        name="Model Alpha",
        model_name="Model Alpha",
        system_type="ml_model",
        lifecycle_status="active",
        deployment_status="production",
        owner_id=user_id,
        created_by_user_id=user_id,
    )
    conn = MLflowConnection(
        organization_id=org_id,
        connection_name="primary",
        ingest_token="tok-s4p1-mlops",
        tracking_server_url=None,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add_all([ai_system, conn])
    db_session.commit()

    svc = MLopsAdapterService(db_session)
    reg = svc.ingest_model_event(
        connection_id=conn.id,
        org_id=org_id,
        event_type="model.deployed",
        model_name="Model Alpha",
        model_version="1",
        stage="production",
    )
    db_session.commit()

    assert reg.auto_risk_created is True
    assert reg.linked_risk_id is not None
    assert _alert_for_risk(db_session, org["organization_id"], reg.linked_risk_id) is not None


def test_s4_p1_appetite_check_audit_finding_accept_risk_creates_breach_alert(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p1-audit")
    _create_threshold(db_session, org["organization_id"], org["user_id"], max_score=5)

    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    engagement = AuditEngagement(
        organization_id=org_id,
        title="Audit S4P1",
        audit_type="internal_readiness",
        scope_framework_ids=[],
        assigned_auditor_ids=[],
        status="planning",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        created_by=user_id,
    )
    db_session.add(engagement)
    db_session.commit()

    svc = AuditFindingService(db_session)
    finding = svc.create_finding_v2(
        org_id,
        engagement.id,
        title="Missing control evidence",
        description="Evidence unavailable during walkthrough",
        severity="critical",
        finding_type="major_nonconformity",
        control_id=None,
        remediation_plan="Document remediation",
        remediation_due_date=date.today() + timedelta(days=10),
        remediation_owner_id=user_id,
        created_by=user_id,
    )
    db_session.commit()

    row = svc.accept_risk(org_id, finding.id, user_id)
    db_session.commit()

    assert row.linked_risk_id is not None
    assert _alert_for_risk(db_session, org["organization_id"], row.linked_risk_id) is not None


def test_s4_p1_appetite_check_compliance_rec_accept_creates_breach_alert(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p1-rec")
    _create_threshold(db_session, org["organization_id"], org["user_id"], max_score=5)

    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    rec = ComplianceRiskRecommendation(
        organization_id=org_id,
        recommendation_type="new_risk",
        title="AI vendor concentration",
        rationale="Single vendor dependency creates resilience risk.",
        suggested_category="operational",
        suggested_likelihood=5,
        suggested_impact=5,
        suggested_treatment="mitigate",
        context_snapshot_json={"source": "test"},
        provider_used="groq",
        used_byo_credentials=False,
        status="pending",
        generated_by=user_id,
    )
    db_session.add(rec)
    db_session.commit()

    svc = ComplianceRiskRecommendationService(db_session)
    updated, created_risk_id = svc.accept_recommendation(
        org_id=org_id,
        recommendation_id=rec.id,
        accepted_by=user_id,
    )
    db_session.commit()

    assert updated.accepted_risk_id is not None
    assert created_risk_id is not None
    assert _alert_for_risk(db_session, org["organization_id"], updated.accepted_risk_id) is not None


def test_s4_p1_appetite_below_threshold_no_false_positive(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p1-no-breach")
    _create_threshold(db_session, org["organization_id"], org["user_id"], max_score=25)

    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    rec = ComplianceRiskRecommendation(
        organization_id=org_id,
        recommendation_type="new_risk",
        title="Minor process inconsistency",
        rationale="Low-priority discrepancy.",
        suggested_category="operational",
        suggested_likelihood=1,
        suggested_impact=1,
        suggested_treatment="mitigate",
        context_snapshot_json={"source": "test"},
        provider_used="groq",
        used_byo_credentials=False,
        status="pending",
        generated_by=user_id,
    )
    db_session.add(rec)
    db_session.commit()

    svc = ComplianceRiskRecommendationService(db_session)
    updated, _ = svc.accept_recommendation(
        org_id=org_id,
        recommendation_id=rec.id,
        accepted_by=user_id,
    )
    db_session.commit()

    assert updated.accepted_risk_id is not None
    assert _alert_for_risk(db_session, org["organization_id"], updated.accepted_risk_id) is None


def test_s4_p1_service_layer_control_evidence_vendor_emit_recalc(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p1-service-recalc")
    org_id = uuid.UUID(org["organization_id"])

    # control status service path
    risk_control = _create_risk(client, org["org_headers"], title="Control linked risk", likelihood=3, impact=3)
    control_id = _create_control(client, org["org_headers"], title="Status control")
    _link_risk_control(client, org["org_headers"], risk_control, control_id)
    _set_risk_score(db_session, risk_control, 1)
    ControlService.set_status(
        db_session,
        organization_id=org_id,
        control_id=uuid.UUID(control_id),
        new_status="implemented",
        triggered_by="service_call",
    )
    db_session.commit()
    risk_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_control))).scalar_one()
    assert risk_row.inherent_score == 9

    # evidence review service path
    risk_evidence = _create_risk(client, org["org_headers"], title="Evidence linked risk", likelihood=4, impact=3)
    control_evidence = _create_control(client, org["org_headers"], title="Evidence control")
    _link_risk_control(client, org["org_headers"], risk_evidence, control_evidence)
    _set_risk_score(db_session, risk_evidence, 1)

    ev = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "Evidence Item", "evidence_type": "attestation"},
    )
    assert ev.status_code == 201
    evidence_id = ev.json()["id"]
    link = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=org["org_headers"],
        json={"control_id": control_evidence},
    )
    assert link.status_code == 200

    EvidenceService(db_session).set_review_status_and_emit(
        org_id,
        uuid.UUID(evidence_id),
        review_status="verified",
        review_notes="ok",
        reviewed_by_user_id=uuid.UUID(org["user_id"]),
        triggered_by="service_call",
    )
    db_session.commit()
    risk_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_evidence))).scalar_one()
    assert risk_row.inherent_score == 12

    # vendor score service path
    risk_vendor = _create_risk(client, org["org_headers"], title="Vendor linked risk", likelihood=5, impact=2)
    control_vendor = _create_control(client, org["org_headers"], title="Vendor control")
    _link_risk_control(client, org["org_headers"], risk_vendor, control_vendor)
    _set_risk_score(db_session, risk_vendor, 1)

    vendor = client.post(
        "/api/v1/compliance/vendors",
        headers=org["org_headers"],
        json={
            "name": "Vendor S4P1",
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
        json={"control_id": control_vendor, "link_reason": "required"},
    )
    assert vendor_link.status_code == 201

    VendorRiskService(db_session).create_risk_score(
        organization_id=org_id,
        vendor_id=uuid.UUID(vendor_id),
        assessment_id=None,
        likelihood="high",
        impact="high",
        notes="service-call",
        scored_by_user_id=uuid.UUID(org["user_id"]),
        triggered_by="service_call",
    )
    db_session.commit()
    risk_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_vendor))).scalar_one()
    assert risk_row.inherent_score == 10

    # vendor score "update" path is append-only via create_risk_score; verify emit/recalc runs again
    _set_risk_score(db_session, risk_vendor, 1)
    VendorRiskService(db_session).create_risk_score(
        organization_id=org_id,
        vendor_id=uuid.UUID(vendor_id),
        assessment_id=None,
        likelihood="medium",
        impact="medium",
        notes="service-call-update",
        scored_by_user_id=uuid.UUID(org["user_id"]),
        triggered_by="service_call",
    )
    db_session.commit()
    risk_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_vendor))).scalar_one()
    assert risk_row.inherent_score == 10
    score_rows = db_session.execute(
        select(VendorRiskScore).where(
            VendorRiskScore.organization_id == org_id,
            VendorRiskScore.vendor_id == uuid.UUID(vendor_id),
        )
    ).scalars().all()
    assert len(score_rows) == 2


def test_s4_p1_api_paths_still_trigger_recalc_via_service_layer(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p1-api-recalc")

    # control path
    risk_id = _create_risk(client, org["org_headers"], title="API control risk", likelihood=3, impact=3)
    control_id = _create_control(client, org["org_headers"], title="API control")
    _link_risk_control(client, org["org_headers"], risk_id, control_id)
    _set_risk_score(db_session, risk_id, 1)

    patch = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=org["org_headers"],
        json={"status": "implemented"},
    )
    assert patch.status_code == 200
    risk_row = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id))).scalar_one()
    assert risk_row.inherent_score == 9

    # evidence path
    risk_id2 = _create_risk(client, org["org_headers"], title="API evidence risk", likelihood=4, impact=3)
    control_id2 = _create_control(client, org["org_headers"], title="API evidence control")
    _link_risk_control(client, org["org_headers"], risk_id2, control_id2)
    _set_risk_score(db_session, risk_id2, 1)

    ev = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "API Ev", "evidence_type": "attestation"},
    )
    assert ev.status_code == 201
    evidence_id = ev.json()["id"]
    link = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=org["org_headers"],
        json={"control_id": control_id2},
    )
    assert link.status_code == 200

    review = client.post(
        f"/api/v1/evidence/{evidence_id}/review",
        headers=org["org_headers"],
        json={"review_status": "verified"},
    )
    assert review.status_code == 200
    risk_row2 = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id2))).scalar_one()
    assert risk_row2.inherent_score == 12

    # vendor path
    risk_id3 = _create_risk(client, org["org_headers"], title="API vendor risk", likelihood=5, impact=2)
    control_id3 = _create_control(client, org["org_headers"], title="API vendor control")
    _link_risk_control(client, org["org_headers"], risk_id3, control_id3)
    _set_risk_score(db_session, risk_id3, 1)

    vendor = client.post(
        "/api/v1/compliance/vendors",
        headers=org["org_headers"],
        json={
            "name": "API Vendor",
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
        json={"control_id": control_id3, "link_reason": "required"},
    )
    assert vendor_link.status_code == 201

    score_resp = client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/risk-scores",
        headers=org["org_headers"],
        json={"likelihood": "high", "impact": "high"},
    )
    assert score_resp.status_code == 201
    risk_row3 = db_session.execute(select(Risk).where(Risk.id == uuid.UUID(risk_id3))).scalar_one()
    assert risk_row3.inherent_score == 10
