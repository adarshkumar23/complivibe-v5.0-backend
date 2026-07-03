from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.board_scorecard_snapshot import BoardScorecardSnapshot
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.entity_risk_score import EntityRiskScore
from app.models.risk import Risk
from app.models.risk_indicator import RiskIndicator
from tests.helpers.auth_org import bootstrap_org_user


def _create_bu(client, headers, name: str, code: str) -> UUID:
    resp = client.post(
        "/api/v1/compliance/business-units",
        headers=headers,
        json={"name": name, "code": code},
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


def test_board_scorecard_snapshot_generation_listing_export_and_immutability(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="bsc-owner")
    headers = owner["org_headers"]
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])

    inspector = inspect(db_session.bind)
    assert "board_scorecard_snapshots" in set(inspector.get_table_names())

    bu_id = _create_bu(client, headers, "Finance", "FIN")
    empty_bu_id = _create_bu(client, headers, "Legal", "LEG")

    # Tagged + untagged records so BU-scoped snapshot differs from org-wide.
    risk_bu = Risk(
        organization_id=org_id,
        title="BU Risk",
        created_by_user_id=user_id,
        business_unit_id=bu_id,
        inherent_score=4,
        severity="high",
    )
    risk_org = Risk(
        organization_id=org_id,
        title="Org Risk",
        created_by_user_id=user_id,
        inherent_score=2,
        severity="medium",
    )
    control_bu = Control(
        organization_id=org_id,
        title="BU Control",
        created_by_user_id=user_id,
        business_unit_id=bu_id,
        status="active",
    )
    control_org = Control(
        organization_id=org_id,
        title="Org Control",
        created_by_user_id=user_id,
        status="active",
    )
    db_session.add_all([risk_bu, risk_org, control_bu, control_org])
    db_session.flush()

    db_session.add(
        EntityRiskScore(
            organization_id=org_id,
            entity_type="business_unit",
            entity_id=bu_id,
            entity_label="Finance",
            composite_score=Decimal("82.50"),
            score_band="critical",
            risk_count=1,
            score_method="equal_weight",
            component_risks_json=[],
            computed_by_user_id=user_id,
        )
    )
    db_session.add(
        ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="risk_threshold_breach",
            severity="high",
            status="open",
            title="BU breach",
            alert_context_json={"scope_id": str(bu_id), "risk_id": str(risk_bu.id)},
        )
    )
    db_session.add(
        RiskIndicator(
            organization_id=org_id,
            name="Overdue Tasks",
            metric_type="overdue_task_rate",
            target_value=Decimal("0.1"),
            warning_threshold=Decimal("0.2"),
            critical_threshold=Decimal("0.3"),
            current_value=Decimal("0.15"),
            status="amber",
            owner_user_id=user_id,
            is_active=True,
        )
    )
    db_session.add(
        ComplianceDeadline(
            organization_id=org_id,
            title="Board Compliance Filing",
            deadline_type="regulatory",
            due_date=date.today() + timedelta(days=10),
            status="upcoming",
            priority="high",
            owner_user_id=user_id,
            created_by_user_id=user_id,
        )
    )
    db_session.commit()

    org_snap_resp = client.post(
        "/api/v1/compliance/board-scorecard/generate",
        headers=headers,
        json={"snapshot_label": "Org-wide"},
    )
    assert org_snap_resp.status_code == 200, org_snap_resp.text
    org_snap = org_snap_resp.json()
    assert org_snap["snapshot_data"]["posture_summary"]["risks"]["total"] >= 2

    bu_snap_resp = client.post(
        "/api/v1/compliance/board-scorecard/generate",
        headers=headers,
        json={"snapshot_label": "BU scoped", "business_unit_id": str(bu_id)},
    )
    assert bu_snap_resp.status_code == 200, bu_snap_resp.text
    bu_snap = bu_snap_resp.json()
    assert bu_snap["snapshot_data"]["posture_summary"]["risks"]["total"] == 1
    assert bu_snap["snapshot_data"]["posture_summary"]["controls"]["total"] == 1
    assert "organization-wide" in bu_snap["snapshot_data"]["framework_readiness"].get("note", "")

    zero_snap_resp = client.post(
        "/api/v1/compliance/board-scorecard/generate",
        headers=headers,
        json={"snapshot_label": "Empty BU", "business_unit_id": str(empty_bu_id)},
    )
    assert zero_snap_resp.status_code == 200, zero_snap_resp.text
    zero_snap = zero_snap_resp.json()
    assert zero_snap["snapshot_data"]["posture_summary"]["risks"]["total"] == 0
    assert zero_snap["snapshot_data"]["posture_summary"]["controls"]["total"] == 0

    list_resp = client.get(
        "/api/v1/compliance/board-scorecard?page=1&page_size=1",
        headers=headers,
    )
    assert list_resp.status_code == 200
    page = list_resp.json()
    assert page["total"] >= 3
    assert len(page["items"]) == 1

    bu_list_resp = client.get(
        f"/api/v1/compliance/board-scorecard?business_unit_id={bu_id}",
        headers=headers,
    )
    assert bu_list_resp.status_code == 200
    bu_items = bu_list_resp.json()["items"]
    assert len(bu_items) >= 1
    assert all(item["business_unit_id"] == str(bu_id) for item in bu_items)

    snapshot_id = UUID(bu_snap["id"])

    owner_b = bootstrap_org_user(client, email_prefix="bsc-other")
    cross = client.get(f"/api/v1/compliance/board-scorecard/{snapshot_id}", headers=owner_b["org_headers"])
    assert cross.status_code == 404

    pdf_resp = client.get(f"/api/v1/compliance/board-scorecard/{snapshot_id}/export?format=pdf", headers=headers)
    assert pdf_resp.status_code == 200, pdf_resp.text
    assert pdf_resp.content[:4] == b"%PDF"

    docx_resp = client.get(f"/api/v1/compliance/board-scorecard/{snapshot_id}/export?format=docx", headers=headers)
    assert docx_resp.status_code == 200, docx_resp.text
    assert docx_resp.content[:2] == b"PK"

    generation_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "board_scorecard.generated",
            AuditLog.entity_id == snapshot_id,
        )
    ).scalars().first()
    assert generation_audit is not None

    export_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "export.generated",
            AuditLog.entity_type == "board_scorecard_snapshot",
            AuditLog.entity_id == snapshot_id,
        )
    ).scalars().first()
    assert export_audit is not None

    put_resp = client.put(f"/api/v1/compliance/board-scorecard/{snapshot_id}", headers=headers, json={})
    patch_resp = client.patch(f"/api/v1/compliance/board-scorecard/{snapshot_id}", headers=headers, json={})
    delete_resp = client.delete(f"/api/v1/compliance/board-scorecard/{snapshot_id}", headers=headers)
    assert put_resp.status_code in {404, 405}
    assert patch_resp.status_code in {404, 405}
    assert delete_resp.status_code in {404, 405}

    # Snapshot row remains immutable/persisted.
    saved = db_session.get(BoardScorecardSnapshot, snapshot_id)
    assert saved is not None
    assert saved.snapshot_data is not None
