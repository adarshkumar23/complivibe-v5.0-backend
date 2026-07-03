import uuid
from datetime import UTC, date, datetime, timedelta

from app.compliance.services.pbc_request_service import PBCRequestService
from app.models.audit_log import AuditLog
from app.models.audit_finding import AuditFinding
from app.models.pbc_request import PBCRequest
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


def _create_audit(client, headers: dict[str, str], title: str = "Sprint 3 Audit") -> dict:
    payload = {
        "title": title,
        "audit_type": "internal_readiness",
        "scope_framework_ids": [],
        "assigned_auditor_ids": [],
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
        "notes": "test",
    }
    response = client.post("/api/v1/compliance/audit-engagements", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_evidence(client, headers: dict[str, str], title: str = "Evidence") -> dict:
    payload = {
        "title": title,
        "description": "Evidence description",
        "evidence_type": "document",
        "source": "manual",
    }
    response = client.post("/api/v1/evidence", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_control(client, headers: dict[str, str], owner_user_id: str, title: str = "Control A") -> dict:
    payload = {
        "title": title,
        "description": "Control description",
        "control_type": "process",
        "criticality": "high",
        "owner_user_id": owner_user_id,
    }
    response = client.post("/api/v1/controls", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_finding(client, headers: dict[str, str], audit_id: str, *, control_id: str | None = None, title: str = "Finding A") -> dict:
    payload = {
        "title": title,
        "description": "Finding description",
        "severity": "high",
        "finding_type": "observation",
        "control_id": control_id,
        "remediation_plan": "Do X",
        "remediation_due_date": (date.today() + timedelta(days=10)).isoformat(),
    }
    response = client.post(f"/api/v1/compliance/audits/{audit_id}/findings", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_s3_p4_pbc_request_lifecycle_and_overdue(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p4-pbc")
    audit = _create_audit(client, org["org_headers"])
    evidence = _create_evidence(client, org["org_headers"])

    bulk = client.post(
        f"/api/v1/compliance/audits/{audit['id']}/pbc-requests/bulk",
        headers=org["org_headers"],
        json={
            "items": [
                {
                    "item_description": "Provide policy index",
                    "assigned_to": org["user_id"],
                    "due_date": (date.today() + timedelta(days=5)).isoformat(),
                },
                {
                    "item_description": "Provide risk register extract",
                    "assigned_to": org["user_id"],
                    "due_date": (date.today() + timedelta(days=5)).isoformat(),
                },
                {
                    "item_description": "Overdue open item",
                    "assigned_to": org["user_id"],
                    "due_date": (date.today() - timedelta(days=2)).isoformat(),
                },
                {
                    "item_description": "Future open item",
                    "assigned_to": org["user_id"],
                    "due_date": (date.today() + timedelta(days=30)).isoformat(),
                },
            ]
        },
    )
    assert bulk.status_code == 201
    payload = bulk.json()
    assert payload["count"] == 4
    assert all(item["status"] == "open" for item in payload["items"])

    request_submit_accept = payload["items"][0]["id"]
    request_submit_reject = payload["items"][1]["id"]
    request_overdue = payload["items"][2]["id"]
    request_future = payload["items"][3]["id"]

    submitted = client.post(
        f"/api/v1/compliance/pbc-requests/{request_submit_accept}/submit",
        headers=org["org_headers"],
        json={"evidence_id": evidence["id"]},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["evidence_id"] == evidence["id"]

    accepted = client.post(
        f"/api/v1/compliance/pbc-requests/{request_submit_accept}/accept",
        headers=org["org_headers"],
        json={},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    submitted2 = client.post(
        f"/api/v1/compliance/pbc-requests/{request_submit_reject}/submit",
        headers=org["org_headers"],
        json={},
    )
    assert submitted2.status_code == 200
    rejected = client.post(
        f"/api/v1/compliance/pbc-requests/{request_submit_reject}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "Insufficient evidence detail"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Insufficient evidence detail"

    overdue_count = PBCRequestService(db_session).mark_overdue(uuid.UUID(org["organization_id"]))
    db_session.commit()
    assert overdue_count == 1

    overdue_row = db_session.query(PBCRequest).filter(PBCRequest.id == uuid.UUID(request_overdue)).one()
    future_row = db_session.query(PBCRequest).filter(PBCRequest.id == uuid.UUID(request_future)).one()
    assert overdue_row.status == "overdue"
    assert future_row.status == "open"

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "pbc.requests_bulk_created" in actions
    assert "pbc.request_submitted" in actions
    assert "pbc.request_accepted" in actions
    assert "pbc.request_rejected" in actions
    assert "pbc.request_overdue" in actions


def test_s3_p4_audit_finding_lifecycle_risk_and_control_health(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p4-find")
    audit = _create_audit(client, org["org_headers"], title="Finding Audit")
    control = _create_control(client, org["org_headers"], org["user_id"], title="Control With Finding")

    created = _create_finding(client, org["org_headers"], audit["id"], control_id=control["id"], title="Finding One")
    finding_id = created["id"]
    assert created["status"] == "open"
    created_row = db_session.query(AuditFinding).filter(AuditFinding.id == uuid.UUID(finding_id)).one()
    assert created_row.title == "Finding One"
    assert created_row.description == "Finding description"
    assert created_row.severity == "high"
    assert created_row.finding_type == "observation"
    assert created_row.status == "open"
    assert created_row.control_id == uuid.UUID(control["id"])
    assert created_row.created_by is not None

    remediated = client.patch(
        f"/api/v1/compliance/audit-findings/{finding_id}/remediation",
        headers=org["org_headers"],
        json={
            "remediation_plan": "Update policy and train owners",
            "remediation_due_date": (date.today() + timedelta(days=7)).isoformat(),
            "remediation_owner_id": org["user_id"],
        },
    )
    assert remediated.status_code == 200
    assert remediated.json()["status"] == "remediation_in_progress"
    remediated_row = db_session.query(AuditFinding).filter(AuditFinding.id == uuid.UUID(finding_id)).one()
    assert remediated_row.remediation_plan == "Update policy and train owners"
    assert remediated_row.remediation_due_date == (date.today() + timedelta(days=7))
    assert remediated_row.remediation_owner_id == uuid.UUID(org["user_id"])

    resolved = client.post(f"/api/v1/compliance/audit-findings/{finding_id}/resolve", headers=org["org_headers"], json={})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    closed = client.post(f"/api/v1/compliance/audit-findings/{finding_id}/close", headers=org["org_headers"], json={})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    finding_for_accept = _create_finding(
        client,
        org["org_headers"],
        audit["id"],
        control_id=control["id"],
        title="Finding Accepted Risk",
    )
    accepted = client.post(
        f"/api/v1/compliance/audit-findings/{finding_for_accept['id']}/accept-risk",
        headers=org["org_headers"],
        json={},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted_risk"
    assert accepted.json()["linked_risk_id"] is not None

    linked_risk = db_session.query(Risk).filter(Risk.id == uuid.UUID(accepted.json()["linked_risk_id"])).one()
    assert linked_risk.title == "Accepted Risk: Finding Accepted Risk"
    assert linked_risk.description == "Finding description"
    assert linked_risk.category == "audit_finding"
    assert linked_risk.status == "identified"
    assert linked_risk.metadata_json is not None
    assert linked_risk.metadata_json.get("auto_created_by") == "complivibe_audit_finding_service"
    assert linked_risk.metadata_json.get("trigger") == "audit_finding_accepted_risk"

    open_finding = _create_finding(
        client,
        org["org_headers"],
        audit["id"],
        control_id=control["id"],
        title="Open Finding Cannot Close",
    )
    close_from_open = client.post(
        f"/api/v1/compliance/audit-findings/{open_finding['id']}/close",
        headers=org["org_headers"],
        json={},
    )
    assert close_from_open.status_code == 409

    health = client.get("/api/v1/compliance/dashboard/control-health", headers=org["org_headers"])
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["open_high_critical_findings"] >= 1
    assert health_payload["health_flag"] == "at_risk"

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "audit_finding.created" in actions
    assert "audit_finding.remediation_updated" in actions
    assert "audit_finding.resolved" in actions
    assert "audit_finding.accepted_risk" in actions
    assert "audit_finding.closed" in actions

    accepted_row = (
        db_session.query(AuditFinding)
        .filter(AuditFinding.id == uuid.UUID(finding_for_accept["id"]))
        .one()
    )
    assert accepted_row.linked_risk_id is not None


def test_s3_p4_cross_org_guards(client):
    org_a = bootstrap_org_user(client, email_prefix="s3p4-org-a")
    org_b = bootstrap_org_user(client, email_prefix="s3p4-org-b")

    audit_a = _create_audit(client, org_a["org_headers"], title="Org A Audit")
    finding_a = _create_finding(client, org_a["org_headers"], audit_a["id"], title="Org A Finding")

    forbidden_bulk = client.post(
        f"/api/v1/compliance/audits/{audit_a['id']}/pbc-requests/bulk",
        headers=org_b["org_headers"],
        json={"items": [{"item_description": "Cross org", "assigned_to": org_b["user_id"]}]},
    )
    assert forbidden_bulk.status_code == 404

    forbidden_finding = client.get(
        f"/api/v1/compliance/audit-findings/{finding_a['id']}",
        headers=org_b["org_headers"],
    )
    assert forbidden_finding.status_code == 404
