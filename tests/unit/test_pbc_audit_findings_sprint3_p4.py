import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.audit_finding import AuditFinding
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


def test_s3_p4_pbc_requests_v2_endpoints_are_deprecated(client):
    """pbc_requests_v2 was a second, parallel PBC model that the dashboard never
    read from -- deprecated in favor of pbc_items (migration 0301 backfilled
    existing data). Every endpoint on this surface should now fail closed with
    410 Gone rather than silently accepting writes nobody will ever see."""
    org = bootstrap_org_user(client, email_prefix="s3p4-pbc")
    audit = _create_audit(client, org["org_headers"])
    fake_id = str(uuid.uuid4())

    bulk = client.post(
        f"/api/v1/compliance/audits/{audit['id']}/pbc-requests/bulk",
        headers=org["org_headers"],
        json={"items": [{"item_description": "Provide policy index", "assigned_to": org["user_id"]}]},
    )
    assert bulk.status_code == 410
    assert "pbc-items" in bulk.json()["detail"]

    listed = client.get(f"/api/v1/compliance/audits/{audit['id']}/pbc-requests", headers=org["org_headers"])
    assert listed.status_code == 410

    get_one = client.get(f"/api/v1/compliance/pbc-requests/{fake_id}", headers=org["org_headers"])
    assert get_one.status_code == 410

    submit = client.post(f"/api/v1/compliance/pbc-requests/{fake_id}/submit", headers=org["org_headers"], json={})
    assert submit.status_code == 410

    accept = client.post(f"/api/v1/compliance/pbc-requests/{fake_id}/accept", headers=org["org_headers"], json={})
    assert accept.status_code == 410

    reject = client.post(
        f"/api/v1/compliance/pbc-requests/{fake_id}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "n/a"},
    )
    assert reject.status_code == 410


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

    # pbc-requests/bulk is deprecated (410 Gone) and no longer does any org lookup at
    # all, so it fails closed before any cross-org check would even run -- see
    # test_s3_p4_pbc_requests_v2_endpoints_are_deprecated for the real coverage.
    forbidden_bulk = client.post(
        f"/api/v1/compliance/audits/{audit_a['id']}/pbc-requests/bulk",
        headers=org_b["org_headers"],
        json={"items": [{"item_description": "Cross org", "assigned_to": org_b["user_id"]}]},
    )
    assert forbidden_bulk.status_code == 410

    forbidden_finding = client.get(
        f"/api/v1/compliance/audit-findings/{finding_a['id']}",
        headers=org_b["org_headers"],
    )
    assert forbidden_finding.status_code == 404
