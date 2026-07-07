from __future__ import annotations

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.roi_calculator_lead import ROICalculatorLead


def test_roi_calculator_public_submit_creates_crm_lead_and_audit(client, db_session):
    response = client.post(
        "/api/v1/roi-calculator",
        json={
            "current_tool": "drata",
            "team_size": 14,
            "frameworks_count": 5,
            "current_annual_cost": 145000.0,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["hours_saved_per_week"] > 0
    assert payload["annual_saving"] > 0
    assert payload["three_year_roi_pct"] is not None
    assert payload["projected_platform_annual_cost"] >= 0
    assert payload["automation_share_pct"] > 0
    assert "context_flags" in payload

    org = db_session.execute(select(Organization).where(Organization.slug == "public-roi-leads")).scalar_one_or_none()
    assert org is not None

    lead = db_session.execute(
        select(ROICalculatorLead).where(ROICalculatorLead.organization_id == org.id).order_by(ROICalculatorLead.created_at.desc())
    ).scalar_one_or_none()
    assert lead is not None
    assert lead.current_tool == "drata"
    assert lead.crm_status == "new"
    assert lead.calculation_inputs_json.get("selected_plan_code") is not None or lead.projected_platform_annual_cost == 0

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id,
            AuditLog.action == "pricing.roi_lead_created",
            AuditLog.entity_id == lead.id,
        )
    ).scalar_one_or_none()
    assert audit is not None


def test_roi_calculator_rejects_invalid_payload(client):
    response = client.post(
        "/api/v1/roi-calculator",
        json={
            "current_tool": "drata",
            "team_size": 0,
            "frameworks_count": 1,
            "current_annual_cost": 25000,
        },
    )
    assert response.status_code == 422

    nan_cost = client.post(
        "/api/v1/roi-calculator",
        json={
            "current_tool": "drata",
            "team_size": 5,
            "frameworks_count": 1,
            "current_annual_cost": "NaN",
        },
    )
    assert nan_cost.status_code == 422


def test_roi_calculator_creates_single_public_org(client, db_session):
    payload = {
        "current_tool": "generic",
        "team_size": 8,
        "frameworks_count": 3,
        "current_annual_cost": 90000.0,
    }
    first = client.post("/api/v1/roi-calculator", json=payload)
    second = client.post("/api/v1/roi-calculator", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200

    org_rows = db_session.execute(select(Organization).where(Organization.slug == "public-roi-leads")).scalars().all()
    assert len(org_rows) == 1


def test_roi_calculator_zero_baseline_sets_context_flags(client):
    response = client.post(
        "/api/v1/roi-calculator",
        json={
            "current_tool": "generic",
            "team_size": 200,
            "frameworks_count": 20,
            "current_annual_cost": 0,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["annual_saving"] == 0
    assert body["net_annual_impact"] <= 0
    assert "baseline_cost_zero" in body["context_flags"]
    assert "high_framework_scope" in body["context_flags"]
    assert "large_team_profile" in body["context_flags"]
