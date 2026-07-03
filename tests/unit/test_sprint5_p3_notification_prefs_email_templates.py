from __future__ import annotations

import uuid
from datetime import UTC, datetime

from jinja2 import Template

from app.models.email_outbox import EmailOutbox
from app.models.email_template import EmailTemplate
from app.models.user_notification_preference import UserNotificationPreference
from app.platform.services.email_outbox_flush_service import EmailOutboxFlushService
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


NOW = datetime.now(UTC)


def _queue_outbox(
    *,
    db_session,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    recipient_email: str,
    event_type: str,
    metadata_json: dict | None = None,
) -> EmailOutbox:
    row = EmailOutbox(
        organization_id=org_id,
        template_id=None,
        event_type=event_type,
        recipient_email=recipient_email,
        recipient_user_id=user_id,
        subject=f"Subject {event_type}",
        body_text=f"Body {event_type}",
        body_html=None,
        status="pending",
        priority="normal",
        scheduled_at=None,
        queued_at=NOW,
        attempt_count=0,
        max_attempts=3,
        metadata_json=metadata_json,
        created_by_user_id=user_id,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_s5_p3_preference_enforcement_skip_and_send(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="s5p3-pref")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    pref = UserNotificationPreference(
        organization_id=org_id,
        user_id=user_id,
        notification_type="digest_weekly",
        channel="none",
        min_severity=None,
        is_enabled=False,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(pref)
    db_session.flush()

    skipped_row = _queue_outbox(
        db_session=db_session,
        org_id=org_id,
        user_id=user_id,
        recipient_email=org["email"],
        event_type="digest.weekly",
    )

    def _should_not_send(**kwargs):
        raise AssertionError("SES send should not be called for preference-skipped notification")

    service = EmailOutboxFlushService(db_session)
    monkeypatch.setattr(service.ses, "send_email", _should_not_send)
    result = service.flush(batch_size=10)

    db_session.refresh(skipped_row)
    assert result["skipped"] >= 1
    assert skipped_row.status == "skipped"

    pref.channel = "email"
    pref.is_enabled = True
    pref.updated_at = datetime.now(UTC)
    db_session.flush()

    send_row = _queue_outbox(
        db_session=db_session,
        org_id=org_id,
        user_id=user_id,
        recipient_email=org["email"],
        event_type="digest.weekly",
    )

    def _ok_send(**kwargs):
        return {"success": True, "message_id": "msg-123"}

    service_enabled = EmailOutboxFlushService(db_session)
    monkeypatch.setattr(service_enabled.ses, "send_email", _ok_send)
    result_enabled = service_enabled.flush(batch_size=10)

    db_session.refresh(send_row)
    assert result_enabled["sent"] >= 1
    assert send_row.status == "sent"


def test_s5_p3_unmapped_event_remains_sendable(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="s5p3-exempt")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    db_session.add(
        UserNotificationPreference(
            organization_id=org_id,
            user_id=user_id,
            notification_type="digest_weekly",
            channel="none",
            min_severity=None,
            is_enabled=False,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    db_session.flush()

    # Unmapped event types are intentionally treated as exempt from preference suppression.
    row = _queue_outbox(
        db_session=db_session,
        org_id=org_id,
        user_id=user_id,
        recipient_email=org["email"],
        event_type="security.critical_alert",
    )

    service = EmailOutboxFlushService(db_session)
    monkeypatch.setattr(service.ses, "send_email", lambda **kwargs: {"success": True, "message_id": "msg-999"})
    result = service.flush(batch_size=10)

    db_session.refresh(row)
    assert result["sent"] >= 1
    assert row.status == "sent"


def test_s5_p3_seeded_email_templates_count_idempotency_and_rendering(db_session):
    first = SeedService.ensure_global_email_templates(db_session)
    second = SeedService.ensure_global_email_templates(db_session)
    assert len(first) == len(second)

    templates = db_session.query(EmailTemplate).filter(EmailTemplate.organization_id.is_(None)).all()
    assert len(templates) >= 9

    by_key = {tpl.template_key: tpl for tpl in templates}
    new_keys = {
        "password_reset",
        "attestation_campaign_reminder",
        "pbc_request_assigned",
        "audit_finding_assigned",
        "vendor_mitigation_case_created",
        "commitment_breach_notification",
    }
    assert new_keys.issubset(set(by_key.keys()))

    for key in new_keys:
        tpl = by_key[key]
        html = tpl.body_html_template or ""
        assert len(html.strip()) > 120
        assert "lorem ipsum" not in html.lower()
        assert "todo" not in html.lower()

        context = {name: f"sample_{name}" for name in (tpl.allowed_variables_json or [])}
        rendered_subject = Template(tpl.subject_template).render(**context)
        rendered_text = Template(tpl.body_text_template).render(**context)
        rendered_html = Template(tpl.body_html_template or "").render(**context)

        assert "{{" not in rendered_subject
        assert "{{" not in rendered_text
        assert "{{" not in rendered_html
