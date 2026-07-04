from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import inspect, select

from app.models.ai_governance_diagnostic_snapshot import AIGovernanceDiagnosticSnapshot
from app.models.ai_system import AISystem
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.mlflow_connection import MLflowConnection
from app.models.mlflow_drift_event import MLflowDriftEvent
from app.models.mlflow_model_registration import MLflowModelRegistration
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


def _make_bu(db_session, org_id: UUID, user_id: UUID, name: str, code: str) -> BusinessUnit:
    row = BusinessUnit(
        organization_id=org_id,
        name=name,
        code=code,
        created_by=user_id,
        is_active=True,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _mk_system(db_session, org_id: UUID, name: str, *, bu_id: UUID | None = None, deployment_status: str = "development") -> AISystem:
    row = AISystem(
        organization_id=org_id,
        name=name,
        system_type="model",
        lifecycle_status="active",
        deployment_status=deployment_status,
        risk_tier="high",
        business_unit_id=bu_id,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _mk_completed_assessment(db_session, org_id: UUID, system_id: UUID, age_days: int = 30) -> None:
    completed_at = datetime.now(UTC) - timedelta(days=age_days)
    db_session.add(
        AISystemRiskAssessment(
            organization_id=org_id,
            ai_system_id=system_id,
            title="Assessment",
            assessment_type="standard",
            status="completed",
            risk_level="medium",
            likelihood="medium",
            impact="medium",
            methodology_version="v1",
            completed_at=completed_at,
        )
    )


def _mk_mlflow_connection(db_session, org_id: UUID) -> MLflowConnection:
    row = MLflowConnection(
        organization_id=org_id,
        connection_name="Prod MLflow",
        ingest_token="token-1234567890",
        tracking_server_url="https://mlflow.example.com",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _mk_mlflow_registration(
    db_session,
    org_id: UUID,
    conn_id: UUID,
    system_id: UUID,
    model_name: str,
    version: str,
) -> None:
    db_session.add(
        MLflowModelRegistration(
            organization_id=org_id,
            mlflow_connection_id=conn_id,
            ai_system_id=system_id,
            model_name=model_name,
            model_version=version,
            stage="production",
            event_type="model.deployed",
            registered_at=datetime.now(UTC) - timedelta(days=5),
            compliance_status="approved",
            auto_linked=True,
            auto_risk_created=False,
            created_at=datetime.now(UTC),
        )
    )


def _mk_drift(db_session, org_id: UUID, conn_id: UUID, system_id: UUID, model_name: str, severity: str = "high") -> None:
    db_session.add(
        MLflowDriftEvent(
            organization_id=org_id,
            mlflow_connection_id=conn_id,
            ai_system_id=system_id,
            model_name=model_name,
            model_version="1",
            drift_metric="psi",
            drift_value=Decimal("0.35"),
            drift_threshold=Decimal("0.15"),
            severity=severity,
            auto_risk_created=False,
            detected_at=datetime.now(UTC) - timedelta(days=2),
            created_at=datetime.now(UTC),
        )
    )


def test_generate_diagnostic_persists_and_summarizes_per_system(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="diag-generate")
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])

    inspector = inspect(db_session.bind)
    assert "ai_governance_diagnostic_snapshots" in set(inspector.get_table_names())

    s1 = _mk_system(db_session, org_id, "System One", deployment_status="deployed")
    s2 = _mk_system(db_session, org_id, "System Two", deployment_status="development")
    _mk_completed_assessment(db_session, org_id, s1.id, age_days=10)
    _mk_completed_assessment(db_session, org_id, s2.id, age_days=40)

    conn = _mk_mlflow_connection(db_session, org_id)
    _mk_mlflow_registration(db_session, org_id, conn.id, s1.id, "System One", "2")

    db_session.add(
        AuditLog(
            organization_id=org_id,
            actor_user_id=user_id,
            action="ai_system.updated",
            entity_type="ai_systems",
            entity_id=s1.id,
            metadata_json={},
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/v1/ai-governance/diagnostics/generate",
        headers=owner["org_headers"],
        json={"snapshot_label": "Initial diagnostic"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["ai_systems_assessed"] == 2
    assert isinstance(body["snapshot_data"]["ai_systems_summary"], list)
    assert len(body["snapshot_data"]["ai_systems_summary"]) == 2
    assert 0 <= float(body["overall_governance_score"]) <= 100
    assert body["overall_health"] in {"good", "needs_attention", "at_risk", "critical"}

    row = db_session.get(AIGovernanceDiagnosticSnapshot, UUID(body["id"]))
    assert row is not None


def test_deployed_without_assessment_marks_critical_and_in_summary(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="diag-critical")
    org_id = UUID(owner["organization_id"])
    _mk_system(db_session, org_id, "NoAssessment", deployment_status="deployed")
    db_session.commit()

    resp = client.post("/api/v1/ai-governance/diagnostics/generate", headers=owner["org_headers"], json={})
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    system = next(item for item in payload["snapshot_data"]["ai_systems_summary"] if item["name"] == "NoAssessment")
    assert system["system_health"] == "critical"
    assert "NoAssessment" in payload["snapshot_data"]["org_level_summary"]["critical_gap_systems"]


def test_diagnostics_regeneration_uses_live_resolution_state(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="diag-live-state")
    org_id = UUID(owner["organization_id"])
    system = _mk_system(db_session, org_id, "LiveState", deployment_status="deployed")

    inactive_conn = _mk_mlflow_connection(db_session, org_id)
    inactive_conn.is_active = False
    _mk_drift(db_session, org_id, inactive_conn.id, system.id, "LiveState", severity="high")
    db_session.commit()

    initial = client.post("/api/v1/ai-governance/diagnostics/generate", headers=owner["org_headers"], json={})
    assert initial.status_code == 200, initial.text
    initial_system = next(item for item in initial.json()["snapshot_data"]["ai_systems_summary"] if item["name"] == "LiveState")
    assert "High/critical model drift detected — no risk raised" in initial_system["governance_gaps"]
    assert "Deployed with no MLflow monitoring connected" in initial_system["governance_gaps"]

    linked_risk = Risk(
        organization_id=org_id,
        title="Resolved drift risk",
        category="ai_governance",
        likelihood=3,
        impact=4,
        inherent_score=12,
        severity="high",
        status="identified",
    )
    db_session.add(linked_risk)
    db_session.flush()
    drift = db_session.execute(
        select(MLflowDriftEvent).where(
            MLflowDriftEvent.organization_id == org_id,
            MLflowDriftEvent.ai_system_id == system.id,
        )
    ).scalar_one()
    drift.linked_risk_id = linked_risk.id
    inactive_conn.is_active = True
    db_session.commit()

    regenerated = client.post("/api/v1/ai-governance/diagnostics/generate", headers=owner["org_headers"], json={})
    assert regenerated.status_code == 200, regenerated.text
    regenerated_system = next(
        item for item in regenerated.json()["snapshot_data"]["ai_systems_summary"] if item["name"] == "LiveState"
    )
    assert "High/critical model drift detected — no risk raised" not in regenerated_system["governance_gaps"]
    assert "Deployed with no MLflow monitoring connected" not in regenerated_system["governance_gaps"]
    assert regenerated_system["active_drift_alerts"] == 1


def test_active_drift_sets_at_risk_and_scoring_formula_known_input(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="diag-score")
    org_id = UUID(owner["organization_id"])

    s1 = _mk_system(db_session, org_id, "Good A", deployment_status="deployed")
    s2 = _mk_system(db_session, org_id, "Critical B", deployment_status="deployed")
    s3 = _mk_system(db_session, org_id, "AtRisk C", deployment_status="deployed")
    s4 = _mk_system(db_session, org_id, "Good D", deployment_status="active")

    _mk_completed_assessment(db_session, org_id, s1.id, age_days=20)
    _mk_completed_assessment(db_session, org_id, s3.id, age_days=15)
    _mk_completed_assessment(db_session, org_id, s4.id, age_days=25)

    conn = _mk_mlflow_connection(db_session, org_id)
    _mk_mlflow_registration(db_session, org_id, conn.id, s1.id, "Good A", "1")
    _mk_mlflow_registration(db_session, org_id, conn.id, s3.id, "AtRisk C", "1")
    _mk_drift(db_session, org_id, conn.id, s3.id, "AtRisk C", severity="high")
    db_session.commit()

    resp = client.post("/api/v1/ai-governance/diagnostics/generate", headers=owner["org_headers"], json={})
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    c_system = next(item for item in payload["snapshot_data"]["ai_systems_summary"] if item["name"] == "AtRisk C")
    assert c_system["active_drift_alerts"] > 0
    assert c_system["system_health"] == "at_risk"

    org_summary = payload["snapshot_data"]["org_level_summary"]
    total = max(int(org_summary["total_ai_systems"]), 1)
    systems_with_completed = int(org_summary["systems_with_completed_assessment"])
    systems_with_mlflow = int(org_summary["systems_with_mlflow_monitoring"])
    systems_with_drift = int(org_summary["systems_with_active_drift_alerts"])
    critical_count = len(org_summary["critical_gap_systems"])
    assert systems_with_mlflow == 2

    expected_score = (
        (0.40 * ((systems_with_completed / total) * 100))
        + (0.25 * ((systems_with_mlflow / total) * 100))
        + (0.20 * (((total - systems_with_drift) / total) * 100))
        + (0.15 * (((total - critical_count) / total) * 100))
    )
    assert abs(float(payload["overall_governance_score"]) - expected_score) <= 0.5
    if expected_score >= 80:
        assert payload["overall_health"] == "good"
    elif expected_score >= 60:
        assert payload["overall_health"] == "needs_attention"
    elif expected_score >= 40:
        assert payload["overall_health"] == "at_risk"
    else:
        assert payload["overall_health"] == "critical"


def test_zero_ai_systems_returns_valid_snapshot(client):
    owner = bootstrap_org_user(client, email_prefix="diag-zero")

    resp = client.post("/api/v1/ai-governance/diagnostics/generate", headers=owner["org_headers"], json={})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ai_systems_assessed"] == 0
    assert float(payload["overall_governance_score"]) == 0.0
    assert payload["overall_health"] == "needs_attention"
    assert payload["snapshot_data"]["ai_systems_summary"] == []


def test_cross_org_isolation_listing_bu_filter_export_audit_and_immutability(client, db_session):
    owner_a = bootstrap_org_user(client, email_prefix="diag-org-a")
    owner_b = bootstrap_org_user(client, email_prefix="diag-org-b")
    org_a = UUID(owner_a["organization_id"])
    user_a = UUID(owner_a["user_id"])

    bu = _make_bu(db_session, org_a, user_a, "Finance", "FIN")
    _mk_system(db_session, org_a, "BU System", bu_id=bu.id, deployment_status="deployed")
    _mk_completed_assessment(db_session, org_a, db_session.execute(select(AISystem.id).where(AISystem.organization_id == org_a)).scalar_one(), age_days=30)
    db_session.commit()

    gen = client.post(
        "/api/v1/ai-governance/diagnostics/generate",
        headers=owner_a["org_headers"],
        json={"business_unit_id": str(bu.id), "snapshot_label": "BU diag"},
    )
    assert gen.status_code == 200, gen.text
    snapshot_id = gen.json()["id"]

    cross = client.get(f"/api/v1/ai-governance/diagnostics/{snapshot_id}", headers=owner_b["org_headers"])
    assert cross.status_code == 404

    listed = client.get(
        f"/api/v1/ai-governance/diagnostics?business_unit_id={bu.id}&page=1&page_size=1",
        headers=owner_a["org_headers"],
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert len(body["items"]) == 1
    assert body["items"][0]["business_unit_id"] == str(bu.id)

    pdf = client.get(
        f"/api/v1/ai-governance/diagnostics/{snapshot_id}/export?format=pdf",
        headers=owner_a["org_headers"],
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"

    docx = client.get(
        f"/api/v1/ai-governance/diagnostics/{snapshot_id}/export?format=docx",
        headers=owner_a["org_headers"],
    )
    assert docx.status_code == 200, docx.text
    assert docx.content[:2] == b"PK"

    gen_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_a,
            AuditLog.action == "ai_governance.diagnostic_generated",
            AuditLog.entity_id == UUID(snapshot_id),
        )
    ).scalars().first()
    assert gen_audit is not None

    export_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_a,
            AuditLog.action == "export.generated",
            AuditLog.entity_type == "ai_governance_diagnostic_snapshot",
            AuditLog.entity_id == UUID(snapshot_id),
        )
    ).scalars().first()
    assert export_audit is not None

    put_resp = client.put(f"/api/v1/ai-governance/diagnostics/{snapshot_id}", headers=owner_a["org_headers"], json={})
    patch_resp = client.patch(f"/api/v1/ai-governance/diagnostics/{snapshot_id}", headers=owner_a["org_headers"], json={})
    delete_resp = client.delete(f"/api/v1/ai-governance/diagnostics/{snapshot_id}", headers=owner_a["org_headers"])
    assert put_resp.status_code in {404, 405}
    assert patch_resp.status_code in {404, 405}
    assert delete_resp.status_code in {404, 405}
