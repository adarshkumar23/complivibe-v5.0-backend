import uuid
from datetime import UTC, date, timedelta

from app.compliance.services.sla_service import SLAService
from app.models.audit_log import AuditLog
from app.models.compliance_bot_outbox import ComplianceBotOutbox
from app.models.compliance_bot_subscription import ComplianceBotSubscription
from app.models.compliance_policy import CompliancePolicy
from app.models.issue import Issue
from app.models.issue_sla_tracking import IssueSLATracking
from app.models.permission import Permission
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.task import Task
from app.models.user import User


def _register(client, email: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!@", "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    response = client.get("/api/v1/organizations/me", headers=_headers(token))
    assert response.status_code == 200
    return response.json()[0]["id"]


def _user(db_session, email: str) -> User:
    return db_session.query(User).filter(User.email == email).one()


def _seed_policy_attestation_record(db_session, org_id: str, user: User) -> PolicyAttestationRecord:
    policy = CompliancePolicy(
        organization_id=uuid.UUID(org_id),
        title="I2 Policy",
        description="Command approval policy",
        policy_type="security",
        status="approved",
        owner_user_id=user.id,
        approved_by_user_id=user.id,
        version="1.0",
    )
    db_session.add(policy)
    db_session.flush()

    campaign = PolicyAttestationCampaign(
        organization_id=uuid.UUID(org_id),
        policy_id=policy.id,
        policy_version="1.0",
        name=f"I2 Campaign {org_id[:8]}",
        description="Bot command campaign",
        due_date=date.today() + timedelta(days=7),
        attestation_expiry_days=30,
        status="active",
        created_by=user.id,
    )
    db_session.add(campaign)
    db_session.flush()

    record = PolicyAttestationRecord(
        organization_id=uuid.UUID(org_id),
        campaign_id=campaign.id,
        user_id=user.id,
        status="pending",
    )
    db_session.add(record)
    db_session.commit()
    return record


def test_i2_slack_approve_command_mutates_attestation_record(client, db_session):
    token = _register(client, "i2-owner-a@example.com", "I2 Org A")
    org_id = _org_id(client, token)
    user = _user(db_session, "i2-owner-a@example.com")
    record = _seed_policy_attestation_record(db_session, org_id, user)

    sub = client.post(
        "/api/v1/compliance-bot/subscriptions",
        headers=_headers(token, org_id),
        json={
            "platform": "slack",
            "channel_ref": "C-I2-ALERTS",
            "digest_enabled": True,
            "digest_time_utc": "08:00",
            "sla_alerts_enabled": True,
        },
    )
    assert sub.status_code == 200, sub.text

    command_response = client.post(
        "/api/v1/compliance-bot/slack/commands",
        headers=_headers(token, org_id),
        json={
            "command": "/complivibe",
            "text": f"approve {record.id}",
            "channel_id": "C-I2-ALERTS",
            "user_id": "U-SLACK-1",
        },
    )
    assert command_response.status_code == 200, command_response.text
    body = command_response.json()
    assert body["command"] == "approve"
    assert body["state_changed"] is True

    db_session.expire_all()
    updated = (
        db_session.query(PolicyAttestationRecord)
        .filter(
            PolicyAttestationRecord.organization_id == uuid.UUID(org_id),
            PolicyAttestationRecord.id == record.id,
        )
        .one()
    )
    assert updated.status == "attested"
    assert updated.attested_at is not None

    command_outbox = (
        db_session.query(ComplianceBotOutbox)
        .filter(
            ComplianceBotOutbox.organization_id == uuid.UUID(org_id),
            ComplianceBotOutbox.message_type == "command_response",
        )
        .first()
    )
    assert command_outbox is not None
    assert command_outbox.status == "sent"

    audit_actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org_id))
        .all()
    }
    assert "attestation.submitted" in audit_actions
    assert "compliance_bot.command_handled" in audit_actions


def test_i2_teams_urgent_command_triggers_sla_breach_state_change(client, db_session):
    token = _register(client, "i2-owner-b@example.com", "I2 Org B")
    org_id = _org_id(client, token)
    user = _user(db_session, "i2-owner-b@example.com")

    issue = Issue(
        organization_id=uuid.UUID(org_id),
        title="Critical SLA issue",
        description="Needs immediate response",
        issue_type="security_incident",
        severity="critical",
        source_type="manual",
        status="open",
        owner_id=user.id,
        assigned_to=None,
        created_by=user.id,
    )
    db_session.add(issue)
    db_session.flush()
    tracking = SLAService(db_session).initialize_tracking_for_issue(issue)
    tracking.response_deadline = SLAService.utcnow() - timedelta(hours=2)
    tracking.response_breached = False
    db_session.commit()

    sub = client.post(
        "/api/v1/compliance-bot/subscriptions",
        headers=_headers(token, org_id),
        json={
            "platform": "teams",
            "channel_ref": "teams-chat-123",
            "digest_enabled": False,
            "digest_time_utc": "08:00",
            "sla_alerts_enabled": True,
        },
    )
    assert sub.status_code == 200

    urgent_response = client.post(
        "/api/v1/compliance-bot/teams/commands",
        headers=_headers(token, org_id),
        json={"text": "/complivibe urgent", "conversation_id": "teams-chat-123"},
    )
    assert urgent_response.status_code == 200, urgent_response.text
    body = urgent_response.json()
    assert body["command"] == "urgent"
    assert body["state_changed"] is True
    assert body["details"]["sla_response_breached"] >= 1

    db_session.expire_all()
    updated_tracking = (
        db_session.query(IssueSLATracking)
        .filter(IssueSLATracking.organization_id == uuid.UUID(org_id), IssueSLATracking.issue_id == issue.id)
        .one()
    )
    assert updated_tracking.response_breached is True


def test_i2_proactive_digest_and_sla_alert_dispatch_queue_outbox(client, db_session):
    token = _register(client, "i2-owner-c@example.com", "I2 Org C")
    org_id = _org_id(client, token)
    user = _user(db_session, "i2-owner-c@example.com")

    now_hhmm = SLAService.utcnow().strftime("%H:%M")
    configure = client.post(
        "/api/v1/compliance-bot/subscriptions",
        headers=_headers(token, org_id),
        json={
            "platform": "slack",
            "channel_ref": "C-I2-PROACTIVE",
            "digest_enabled": True,
            "digest_time_utc": now_hhmm,
            "sla_alerts_enabled": True,
        },
    )
    assert configure.status_code == 200

    task = Task(
        organization_id=uuid.UUID(org_id),
        title="Overdue for digest",
        description="Task should appear in digest",
        status="open",
        priority="high",
        task_type="general",
        owner_user_id=user.id,
        created_by_user_id=user.id,
        due_date=SLAService.utcnow() - timedelta(days=1),
        source="manual",
        reminder_status="none",
    )
    db_session.add(task)

    issue = Issue(
        organization_id=uuid.UUID(org_id),
        title="SLA dispatch issue",
        description="Issue that should breach",
        issue_type="security_incident",
        severity="high",
        source_type="manual",
        status="open",
        owner_id=user.id,
        assigned_to=None,
        created_by=user.id,
    )
    db_session.add(issue)
    db_session.flush()
    tracking = SLAService(db_session).initialize_tracking_for_issue(issue)
    tracking.response_deadline = SLAService.utcnow() - timedelta(hours=5)
    tracking.response_breached = False
    db_session.commit()

    digest_run = client.post("/api/v1/compliance-bot/proactive/run-digest", headers=_headers(token, org_id))
    assert digest_run.status_code == 200, digest_run.text
    assert digest_run.json()["queued_messages"] >= 1

    sla_run = client.post("/api/v1/compliance-bot/proactive/run-sla-alerts", headers=_headers(token, org_id))
    assert sla_run.status_code == 200, sla_run.text
    assert sla_run.json()["queued_messages"] >= 1

    outbox_rows = (
        db_session.query(ComplianceBotOutbox)
        .filter(
            ComplianceBotOutbox.organization_id == uuid.UUID(org_id),
            ComplianceBotOutbox.message_type.in_(["daily_digest", "sla_alert"]),
        )
        .all()
    )
    assert any(row.message_type == "daily_digest" and row.status == "pending" for row in outbox_rows)
    assert any(row.message_type == "sla_alert" and row.status == "pending" for row in outbox_rows)

    permission_keys = {row.key for row in db_session.query(Permission).all()}
    assert {
        "compliance_bot:configure_subscription",
        "compliance_bot:list_subscriptions",
        "compliance_bot:slack_command",
        "compliance_bot:teams_command",
        "compliance_bot:run_digest",
        "compliance_bot:run_sla_alerts",
        "compliance_bot:read_outbox",
    }.issubset(permission_keys)

    subscription = (
        db_session.query(ComplianceBotSubscription)
        .filter(ComplianceBotSubscription.organization_id == uuid.UUID(org_id), ComplianceBotSubscription.user_id == user.id)
        .one()
    )
    assert subscription.last_digest_sent_at is not None
    assert subscription.last_sla_alert_sent_at is not None
