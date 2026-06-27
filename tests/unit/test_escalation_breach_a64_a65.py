from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.breach_notification import BreachNotification
from app.models.email_outbox import EmailOutbox
from app.models.escalation_event import EscalationEvent
from app.models.issue import Issue
from app.models.issue_sla_tracking import IssueSLATracking
from tests.helpers.auth_org import bootstrap_org_user


ISSUES_BASE = "/api/v1/compliance/issues"
ESCALATIONS_BASE = "/api/v1/compliance/escalation-policies"
BREACH_BASE = "/api/v1/compliance/breach-notifications"


def _create_issue(
    client,
    headers: dict[str, str],
    *,
    owner_id: str,
    issue_type: str = "security_incident",
    severity: str = "high",
    title: str = "Issue",
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


def _invite_compliance_manager(client, org_headers: dict[str, str], email: str) -> None:
    invite = client.post(
        "/api/v1/memberships",
        headers=org_headers,
        json={"email": email, "role_name": "compliance_manager", "status": "active"},
    )
    assert invite.status_code == 201


def test_a64_escalation_policy_create_evaluate_idempotency_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a64-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a64-org-b")

    stuck_issue = _create_issue(client, org_a["org_headers"], owner_id=org_a["user_id"], severity="critical", title="stuck")
    issue_row = db_session.get(Issue, uuid.UUID(stuck_issue["id"]))
    assert issue_row is not None
    issue_row.updated_at = datetime.now(UTC) - timedelta(hours=5)
    db_session.commit()

    time_policy = client.post(
        ESCALATIONS_BASE,
        headers=org_a["org_headers"],
        json={
            "name": "Issue stuck >2h",
            "entity_type": "issue",
            "condition_type": "time_in_state",
            "condition_value": {"hours": 2},
            "escalate_to_user_id": org_a["user_id"],
            "notification_message_template": "Escalation {entity_type} {entity_id} by {condition_type}",
        },
    )
    assert time_policy.status_code == 201

    eval1 = client.post(f"{ESCALATIONS_BASE}/evaluate", headers=org_a["org_headers"])
    assert eval1.status_code == 200
    assert eval1.json()["escalations_fired"] >= 1

    eval2 = client.post(f"{ESCALATIONS_BASE}/evaluate", headers=org_a["org_headers"])
    assert eval2.status_code == 200
    assert eval2.json()["escalations_fired"] == 0
    assert eval2.json()["skipped_idempotent"] >= 1

    escalation_events = db_session.query(EscalationEvent).filter(
        EscalationEvent.organization_id == uuid.UUID(org_a["organization_id"]),
        EscalationEvent.entity_id == uuid.UUID(stuck_issue["id"]),
    ).all()
    assert len(escalation_events) == 1

    outbox_count = db_session.query(EmailOutbox).filter(
        EmailOutbox.organization_id == uuid.UUID(org_a["organization_id"]),
        EmailOutbox.event_type == "escalation.policy_triggered",
    ).count()
    assert outbox_count >= 1

    list_org_b = client.get(ESCALATIONS_BASE, headers=org_b["org_headers"])
    assert list_org_b.status_code == 200
    assert all(row["organization_id"] == org_b["organization_id"] for row in list_org_b.json())


def test_a64_escalation_sla_breach_and_deactivated_policy_not_evaluated(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a64-sla")

    sla_issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], issue_type="custom", severity="high", title="sla")
    tracking = db_session.query(IssueSLATracking).filter(
        IssueSLATracking.issue_id == uuid.UUID(sla_issue["id"])
    ).one()
    tracking.response_breached = True
    db_session.commit()

    breach_policy = client.post(
        ESCALATIONS_BASE,
        headers=org["org_headers"],
        json={
            "name": "SLA breached issue",
            "entity_type": "issue",
            "condition_type": "sla_breach",
            "condition_value": {},
            "escalate_to_user_id": org["user_id"],
            "notification_message_template": "Escalate {entity_type} {entity_id}",
        },
    )
    assert breach_policy.status_code == 201

    evaluate = client.post(f"{ESCALATIONS_BASE}/evaluate", headers=org["org_headers"])
    assert evaluate.status_code == 200
    assert evaluate.json()["escalations_fired"] >= 1

    deactivated = client.post(f"{ESCALATIONS_BASE}/{breach_policy.json()['id']}/deactivate", headers=org["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # Move out of 24h idempotency window and verify deactivated policy is still skipped.
    event_rows = db_session.query(EscalationEvent).filter(EscalationEvent.policy_id == uuid.UUID(breach_policy.json()["id"])).all()
    for row in event_rows:
        row.escalated_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.commit()

    evaluate_after_deactivate = client.post(f"{ESCALATIONS_BASE}/evaluate", headers=org["org_headers"])
    assert evaluate_after_deactivate.status_code == 200
    assert evaluate_after_deactivate.json()["escalations_fired"] == 0


def test_a65_breach_creation_deadlines_transitions_and_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a65-breach")

    issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], issue_type="security_incident")
    created_at = datetime.fromisoformat(issue["created_at"])

    gdpr = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "personal_data_affected": True,
            "regulatory_notification_required": True,
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
            "subject_notification_required": True,
        },
    )
    assert gdpr.status_code == 201
    breach_id = gdpr.json()["id"]

    deadline = datetime.fromisoformat(gdpr.json()["regulatory_notification_deadline"])
    assert deadline == created_at + timedelta(hours=72)

    duplicate = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "regulatory_notification_required": True,
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
        },
    )
    assert duplicate.status_code == 409

    wrong_type_issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], issue_type="compliance_violation")
    wrong_type = client.post(
        f"{ISSUES_BASE}/{wrong_type_issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "financial",
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
        },
    )
    assert wrong_type.status_code == 422

    hipaa_issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], issue_type="data_loss")
    hipaa_created = client.post(
        f"{ISSUES_BASE}/{hipaa_issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "health",
            "regulatory_framework": "hipaa",
            "regulatory_notification_hours": 1440,
            "regulatory_notification_required": True,
        },
    )
    assert hipaa_created.status_code == 201
    hipaa_deadline = datetime.fromisoformat(hipaa_created.json()["regulatory_notification_deadline"])
    hipaa_created_at = datetime.fromisoformat(hipaa_issue["created_at"])
    assert hipaa_deadline == hipaa_created_at + timedelta(hours=1440)

    regulator_notified = client.post(f"{BREACH_BASE}/{breach_id}/record-regulator-notification", headers=org["org_headers"])
    assert regulator_notified.status_code == 200
    assert regulator_notified.json()["status"] == "regulator_notified"
    assert regulator_notified.json()["regulatory_notified_at"] is not None

    subject_notified = client.post(f"{BREACH_BASE}/{breach_id}/record-subject-notification", headers=org["org_headers"])
    assert subject_notified.status_code == 200
    assert subject_notified.json()["status"] == "subjects_notified"
    assert subject_notified.json()["subjects_notified_at"] is not None

    close_issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], issue_type="unauthorized_access")
    close_breach = client.post(
        f"{ISSUES_BASE}/{close_issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "confidential",
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
        },
    )
    assert close_breach.status_code == 201
    closed = client.post(f"{BREACH_BASE}/{close_breach.json()['id']}/close", headers=org["org_headers"])
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_a65_breach_deadline_sweep_and_admin_permission_guard(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a65-sweep")
    reviewer = bootstrap_org_user(client, email_prefix="a65-reviewer")
    _invite_compliance_manager(client, org["org_headers"], reviewer["email"])

    reviewer_headers = {
        "Authorization": f"Bearer {reviewer['access_token']}",
        "X-Organization-ID": org["organization_id"],
    }

    issue = _create_issue(client, org["org_headers"], owner_id=org["user_id"], issue_type="security_incident")
    forbidden = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=reviewer_headers,
        json={
            "breach_type": "personal_data",
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
            "regulatory_notification_required": True,
        },
    )
    assert forbidden.status_code == 403

    created = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
            "regulatory_notification_required": True,
        },
    )
    assert created.status_code == 201

    row = db_session.get(BreachNotification, uuid.UUID(created.json()["id"]))
    assert row is not None
    row.regulatory_notification_deadline = datetime.now(UTC) + timedelta(hours=5)
    row.regulatory_notified_at = None
    row.status = "assessing"
    db_session.commit()

    from app.compliance.services.breach_notification_service import BreachNotificationService

    sweep = BreachNotificationService(db_session).sweep_breach_deadlines()
    db_session.commit()
    assert sweep["warned"] >= 1
    assert sweep["transitioned"] >= 1

    refreshed = db_session.get(BreachNotification, uuid.UUID(created.json()["id"]))
    assert refreshed is not None
    assert refreshed.status == "notification_due"

    outbox_count = db_session.query(EmailOutbox).filter(
        EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
        EmailOutbox.event_type == "breach_notification.deadline_warning",
    ).count()
    assert outbox_count >= 1

    # Already notified breach should not be warned again.
    refreshed.regulatory_notified_at = datetime.now(UTC)
    db_session.commit()

    sweep2 = BreachNotificationService(db_session).sweep_breach_deadlines()
    db_session.commit()
    assert sweep2["warned"] == 0
