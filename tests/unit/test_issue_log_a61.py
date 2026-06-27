from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.audit_engagement import AuditEngagement
from app.models.audit_finding import AuditFinding
from app.models.audit_log import AuditLog
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.issue_transition import IssueTransition
from tests.helpers.auth_org import bootstrap_org_user, org_headers


ISSUES_BASE = "/api/v1/compliance/issues"
SETTINGS_BASE = "/api/v1/compliance/issue-settings"


def _create_issue(
    client,
    headers: dict[str, str],
    *,
    owner_id: str,
    title: str = "Issue",
    issue_type: str = "custom",
    severity: str = "medium",
) -> dict:
    response = client.post(
        ISSUES_BASE,
        headers=headers,
        json={
            "title": title,
            "description": "Issue description",
            "issue_type": issue_type,
            "severity": severity,
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_a61_create_issue_types_and_invalid_type(client):
    org = bootstrap_org_user(client, email_prefix="a61-types")

    issue_types = [
        "security_incident",
        "compliance_violation",
        "operational_failure",
        "vendor_failure",
        "data_loss",
        "unauthorized_access",
        "policy_violation",
        "custom",
    ]
    for idx, issue_type in enumerate(issue_types):
        created = _create_issue(
            client,
            org["org_headers"],
            owner_id=org["user_id"],
            title=f"Issue Type {idx}",
            issue_type=issue_type,
        )
        assert created["issue_type"] == issue_type

    invalid = client.post(
        ISSUES_BASE,
        headers=org["org_headers"],
        json={
            "title": "Invalid type",
            "description": "invalid",
            "issue_type": "not_real",
            "severity": "high",
            "owner_id": org["user_id"],
        },
    )
    assert invalid.status_code == 422


def test_a61_issue_transitions_chain_guards_timestamps_and_transition_log(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a61-transitions")
    issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], title="Transition target")

    skipped = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "mitigating"},
    )
    assert skipped.status_code == 422

    step1 = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "investigating", "notes": "triage started"},
    )
    assert step1.status_code == 200
    assert step1.json()["status"] == "investigating"

    step2 = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "mitigating"},
    )
    assert step2.status_code == 200
    assert step2.json()["status"] == "mitigating"

    step3 = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "resolved"},
    )
    assert step3.status_code == 200
    assert step3.json()["status"] == "resolved"
    assert step3.json()["resolved_at"] is not None

    reverse = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "investigating"},
    )
    assert reverse.status_code == 422

    no_resolution_note = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed"},
    )
    assert no_resolution_note.status_code == 422

    create_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={
            "summary": "Transition RCA",
            "timeline_description": "Issue timeline",
            "root_cause": "Root cause documented",
            "contributing_factors": [],
            "corrective_actions": [],
            "preventive_measures": [],
        },
    )
    assert create_rca.status_code == 201

    close_ok = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed", "resolution_note": "Containment complete"},
    )
    assert close_ok.status_code == 200
    assert close_ok.json()["status"] == "closed"
    assert close_ok.json()["closed_at"] is not None
    assert close_ok.json()["resolution_note"] == "Containment complete"

    closed_terminal = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "resolved"},
    )
    assert closed_terminal.status_code == 422

    history = client.get(f"{ISSUES_BASE}/{issue['id']}/transitions", headers=org["org_headers"])
    assert history.status_code == 200
    payload = history.json()
    assert [item["to_status"] for item in payload] == ["investigating", "mitigating", "resolved", "closed"]

    transition_rows = db_session.query(IssueTransition).filter(
        IssueTransition.issue_id == uuid.UUID(issue["id"])
    ).all()
    assert len(transition_rows) == 4


def test_a61_assign_promotions_dashboard_delete_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a61-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a61-org-b")

    critical = _create_issue(
        client,
        org_a["org_headers"],
        owner_id=org_a["user_id"],
        title="Critical issue",
        severity="critical",
    )
    medium = _create_issue(
        client,
        org_a["org_headers"],
        owner_id=org_a["user_id"],
        title="Medium issue",
        severity="medium",
    )

    assigned = client.post(
        f"{ISSUES_BASE}/{critical['id']}/assign",
        headers=org_a["org_headers"],
        json={"assigned_to": org_a["user_id"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to"] == org_a["user_id"]

    assign_log = db_session.query(AuditLog).filter(
        AuditLog.organization_id == uuid.UUID(org_a["organization_id"]),
        AuditLog.action == "issue.assigned",
        AuditLog.entity_id == uuid.UUID(critical["id"]),
    ).first()
    assert assign_log is not None

    dashboard = client.get(f"{ISSUES_BASE}/dashboard", headers=org_a["org_headers"])
    assert dashboard.status_code == 200
    summary = dashboard.json()
    assert summary["by_severity"]["critical"] >= 1
    assert summary["by_severity"]["medium"] >= 1

    to_block_delete = _create_issue(
        client,
        org_a["org_headers"],
        owner_id=org_a["user_id"],
        title="Delete blocked",
    )
    transitioned = client.post(
        f"{ISSUES_BASE}/{to_block_delete['id']}/transition",
        headers=org_a["org_headers"],
        json={"new_status": "investigating"},
    )
    assert transitioned.status_code == 200
    blocked_delete = client.delete(f"{ISSUES_BASE}/{to_block_delete['id']}", headers=org_a["org_headers"])
    assert blocked_delete.status_code == 422

    not_found_other_org = client.get(f"{ISSUES_BASE}/{medium['id']}", headers=org_b["org_headers"])
    assert not_found_other_org.status_code == 404

    alert = ControlMonitoringAlert(
        organization_id=uuid.UUID(org_a["organization_id"]),
        alert_type="config_drift",
        severity="high",
        status="open",
        title="Drift alert",
        description="MFA disabled",
    )
    db_session.add(alert)
    db_session.commit()

    from_alert = client.post(
        f"/api/v1/compliance/monitoring/alerts/{alert.id}/create-issue",
        headers=org_a["org_headers"],
        json={
            "title": "Issue from alert",
            "description": "Promoted from monitoring alert",
            "issue_type": "security_incident",
            "severity": "high",
            "owner_id": org_a["user_id"],
        },
    )
    assert from_alert.status_code == 201
    assert from_alert.json()["source_type"] == "monitoring_alert"
    assert from_alert.json()["source_id"] == str(alert.id)

    engagement = AuditEngagement(
        organization_id=uuid.UUID(org_a["organization_id"]),
        title="Annual external audit",
        audit_type="external_certification",
        scope_framework_ids=[],
        assigned_auditor_ids=[],
        status="planning",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        created_by=uuid.UUID(org_a["user_id"]),
    )
    db_session.add(engagement)
    db_session.flush()

    finding = AuditFinding(
        organization_id=uuid.UUID(org_a["organization_id"]),
        audit_engagement_id=engagement.id,
        finding_ref="F-2026-001",
        severity="high",
        framework_ref="SOC2 CC6.1",
        title="Audit finding",
        description="Weak access control",
        assigned_owner_id=uuid.UUID(org_a["user_id"]),
        remediation_action="Enable MFA",
        target_remediation_date=date.today() + timedelta(days=14),
        status="open",
        risk_register_entry_id=None,
        control_id=None,
    )
    db_session.add(finding)
    db_session.commit()

    from_finding = client.post(
        f"/api/v1/compliance/audit-findings/{finding.id}/create-issue",
        headers=org_a["org_headers"],
        json={
            "title": "Issue from finding",
            "description": "Promoted from audit finding",
            "issue_type": "compliance_violation",
            "severity": "high",
            "owner_id": org_a["user_id"],
        },
    )
    assert from_finding.status_code == 201
    assert from_finding.json()["source_type"] == "audit_finding"
    assert from_finding.json()["source_id"] == str(finding.id)


def test_a61_issue_settings_requires_admin_permission(client):
    org_a = bootstrap_org_user(client, email_prefix="a61-settings-a")
    org_b = bootstrap_org_user(client, email_prefix="a61-settings-b")

    settings_read = client.get(SETTINGS_BASE, headers=org_a["org_headers"])
    assert settings_read.status_code == 200
    assert settings_read.json()["require_rca_before_close"] is True

    owner_update = client.patch(
        SETTINGS_BASE,
        headers=org_a["org_headers"],
        json={"require_rca_before_close": False},
    )
    assert owner_update.status_code == 200
    assert owner_update.json()["require_rca_before_close"] is False

    invite_readonly = client.post(
        "/api/v1/memberships",
        headers=org_a["org_headers"],
        json={
            "email": org_b["email"],
            "role_name": "readonly",
            "status": "active",
        },
    )
    assert invite_readonly.status_code == 201

    readonly_headers_in_org_a = org_headers(org_b["access_token"], org_a["organization_id"])
    denied = client.patch(
        SETTINGS_BASE,
        headers=readonly_headers_in_org_a,
        json={"require_rca_before_close": True},
    )
    assert denied.status_code == 403
