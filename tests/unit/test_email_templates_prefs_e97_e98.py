from __future__ import annotations

import uuid

import pytest
from jinja2 import TemplateNotFound

from app.compliance.services.email_template_service import EmailTemplateService
from app.models.user_notification_preference import UserNotificationPreference
from app.privacy.services.notification_preference_service import NotificationPreferenceService
from tests.helpers.auth_org import bootstrap_org_user


def test_e97_email_template_service_renderers():
    service = EmailTemplateService()

    subject, html = service.render_task_assigned(
        task_title="Complete SOC2 remediation",
        due_date="2026-07-15",
        assigned_by="Alex",
        description="Finish remediation evidence",
        org_name="Acme Corp",
    )
    assert "Complete SOC2 remediation" in subject
    assert "Acme Corp" in html
    assert "2026-07-15" in html
    assert "automated notification from CompliVibe" in html

    _, urgent_html = service.render_breach_notification_due(
        breach_type="Data leak",
        supervisory_authority="ICO",
        deadline="2026-07-01T10:00:00Z",
        hours_remaining=4,
        org_name="Acme Corp",
    )
    assert 'class="urgent"' in urgent_html

    _, normal_html = service.render_breach_notification_due(
        breach_type="Data leak",
        supervisory_authority="ICO",
        deadline="2026-07-01T10:00:00Z",
        hours_remaining=48,
        org_name="Acme Corp",
    )
    assert 'class="urgent"' not in normal_html

    with pytest.raises(TemplateNotFound):
        service.render("does_not_exist.html", {"subject": "x"}, "Acme Corp")


def test_e98_notification_preferences_service(client, db_session):
    org = bootstrap_org_user(client, email_prefix="e98-org")
    org_b = bootstrap_org_user(client, email_prefix="e98-org-b")

    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    service = NotificationPreferenceService(db_session)

    created = service.get_or_create_preferences(org_id, user_id)
    assert len(created) == 12
    assert all(item.channel == "email" for item in created)
    assert all(item.is_enabled is True for item in created)

    second = service.get_or_create_preferences(org_id, user_id)
    assert len(second) == 12
    count = (
        db_session.query(UserNotificationPreference)
        .filter(
            UserNotificationPreference.organization_id == org_id,
            UserNotificationPreference.user_id == user_id,
        )
        .count()
    )
    assert count == 12

    updated = service.update_preference(
        org_id,
        user_id,
        "task_assigned",
        channel="none",
        is_enabled=True,
        min_severity=None,
    )
    assert updated.channel == "none"
    assert updated.is_enabled is False

    assert service.should_notify(org_id, user_id, "task_assigned", severity="critical") is False

    service.update_preference(
        org_id,
        user_id,
        "sla_breach",
        channel="email",
        is_enabled=False,
        min_severity=None,
    )
    assert service.should_notify(org_id, user_id, "sla_breach", severity="critical") is False

    service.update_preference(
        org_id,
        user_id,
        "risk_escalated",
        channel="email",
        is_enabled=True,
        min_severity="high",
    )
    assert service.should_notify(org_id, user_id, "risk_escalated", severity="low") is False
    assert service.should_notify(org_id, user_id, "risk_escalated", severity="critical") is True

    service.update_preference(
        org_id,
        user_id,
        "deadline_approaching",
        channel="email",
        is_enabled=True,
        min_severity=None,
    )
    assert service.should_notify(org_id, user_id, "deadline_approaching", severity="low") is True

    bulk = service.bulk_update_preferences(
        org_id,
        user_id,
        updates=[
            {"notification_type": "digest_daily", "channel": "in_app", "is_enabled": True, "min_severity": None},
            {"notification_type": "digest_weekly", "channel": "none", "is_enabled": True, "min_severity": None},
        ],
    )
    assert len(bulk) == 2

    foreign_should = NotificationPreferenceService(db_session).should_notify(
        uuid.UUID(org_b["organization_id"]),
        uuid.UUID(org_b["user_id"]),
        "task_assigned",
        severity="critical",
    )
    assert foreign_should is True
