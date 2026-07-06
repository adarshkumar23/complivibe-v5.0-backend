from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.compliance.services.digest_service import DigestService
from app.compliance.services.email_template_service import EmailTemplateService
from app.ai_governance.services.ai_provider_service import AIProviderService
from app.models.compliance_deadline import ComplianceDeadline
from app.models.digest_config import DigestConfig
from app.models.email_outbox import EmailOutbox
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.org_email_config import OrgEmailConfig
from app.models.risk import Risk
from app.models.task import Task
from app.models.user_notification_preference import UserNotificationPreference
from tests.helpers.auth_org import bootstrap_org_user


def test_e99_digest_configs_and_content_and_send(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="e99-org")
    org_b = bootstrap_org_user(client, email_prefix="e99-org-b")

    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    now = datetime.now(UTC)

    service = DigestService(db_session)

    def _fake_provider_chain(self, *, org_id, messages, failure_context):  # noqa: ANN001
        return ("Focus first on overdue tasks and critical risk treatment, then clear near-term evidence and deadline items.", "groq", False)

    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)

    # Create defaults and ensure unique by org/user/type via get_or_create upsert pattern.
    rows = service.get_or_create_configs(org_id, user_id)
    assert len(rows) == 2
    rows_again = service.get_or_create_configs(org_id, user_id)
    assert len(rows_again) == 2
    count = (
        db_session.query(DigestConfig)
        .filter(DigestConfig.organization_id == org_id, DigestConfig.user_id == user_id)
        .count()
    )
    assert count == 2

    # Seed data used by daily digest sections.
    db_session.add(
        Task(
            organization_id=org_id,
            title="Overdue task",
            description="x",
            status="open",
            priority="high",
            task_type="general",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            due_date=now - timedelta(days=2),
            metadata_json={},
        )
    )
    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="SOC2 Evidence",
            description="x",
            evidence_type="document",
            source="manual",
            status="active",
            review_status="not_reviewed",
            freshness_status="unknown",
            valid_until=now + timedelta(days=10),
            metadata_json={},
        )
    )
    db_session.add(
        Risk(
            organization_id=org_id,
            title="Critical risk",
            description="x",
            category="security",
            severity="critical",
            likelihood=5,
            impact=5,
            inherent_score=25,
            status="open",
            treatment_strategy="mitigate",
            owner_user_id=user_id,
            metadata_json={},
            created_by_user_id=user_id,
        )
    )
    db_session.add(
        ComplianceDeadline(
            organization_id=org_id,
            title="Deadline 1",
            description="x",
            deadline_type="obligation",
            due_date=(now + timedelta(days=3)).date(),
            status="upcoming",
            priority="high",
            owner_user_id=user_id,
            reminder_days_before=7,
            created_by_user_id=user_id,
            tags_json={},
            notes=None,
        )
    )

    # Org isolation seed: should not appear in org A digest.
    db_session.add(
        Task(
            organization_id=uuid.UUID(org_b["organization_id"]),
            title="Org B task",
            description="x",
            status="open",
            priority="high",
            task_type="general",
            owner_user_id=uuid.UUID(org_b["user_id"]),
            created_by_user_id=uuid.UUID(org_b["user_id"]),
            due_date=now - timedelta(days=3),
            metadata_json={},
        )
    )

    # Weekly add-on metrics.
    db_session.add(
        Issue(
            organization_id=org_id,
            title="Issue this week",
            description="desc",
            issue_type="custom",
            severity="high",
            source_type="manual",
            status="open",
            owner_id=user_id,
            assigned_to=user_id,
            created_by=user_id,
            deleted_at=None,
        )
    )

    # Active email config required for send_digest queue path.
    db_session.add(
        OrgEmailConfig(
            organization_id=org_id,
            provider="ses",
            config_json="stub",
            is_active=True,
            test_sent_at=None,
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    daily = service.build_daily_digest(org_id, user_id, db_session)
    assert set(daily.keys()) >= {"overdue_tasks", "expiring_evidence", "open_risks", "upcoming_deadlines"}
    assert len(daily["overdue_tasks"]) == 1
    assert len(daily["expiring_evidence"]) == 1
    assert len(daily["open_risks"]) == 1
    assert len(daily["upcoming_deadlines"]) == 1
    assert all("Org B task" not in item["title"] for item in daily["overdue_tasks"])

    empty_daily = service.build_daily_digest(uuid.UUID(org_b["organization_id"]), user_id, db_session)
    assert empty_daily["overdue_tasks"] == []
    assert empty_daily["expiring_evidence"] == []
    assert empty_daily["open_risks"] == []
    assert empty_daily["upcoming_deadlines"] == []

    weekly = service.build_weekly_digest(org_id, user_id, db_session)
    assert "new_issues_this_week" in weekly
    assert "obligations_due_this_month" in weekly

    # Opt-out via preferences should prevent queue.
    pref = UserNotificationPreference(
        organization_id=org_id,
        user_id=user_id,
        notification_type="digest_daily",
        channel="none",
        min_severity=None,
        is_enabled=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(pref)
    db_session.commit()

    sent_opt_out = service.send_digest(org_id, user_id, "daily", db_session)
    assert sent_opt_out is False

    # Opt-in should queue outbox row.
    pref.channel = "email"
    pref.is_enabled = True
    pref.updated_at = datetime.now(UTC)
    db_session.commit()

    sent_opt_in = service.send_digest(org_id, user_id, "daily", db_session)
    assert sent_opt_in is True
    queued = (
        db_session.query(EmailOutbox)
        .filter(EmailOutbox.organization_id == org_id, EmailOutbox.event_type == "digest.daily")
        .all()
    )
    assert len(queued) >= 1
    latest = queued[-1]
    assert "narrative_paragraph" in (latest.template_context or {})
    assert (latest.template_context or {}).get("narrative_source") in {"ai_groq", "ai_azure", "deterministic_fallback", "deterministic_empty"}

    tpl = EmailTemplateService()
    subject_daily, html_daily = tpl.render(
        "digest_daily.html",
        {
            "subject": "Daily",
            "user_name": org["email"],
            **daily,
        },
        org_name="Acme",
    )
    assert subject_daily == "Daily"
    assert isinstance(html_daily, str)
    assert len(html_daily) > 0

    subject_weekly, html_weekly = tpl.render(
        "digest_weekly.html",
        {
            "subject": "Weekly",
            "user_name": org["email"],
            **weekly,
        },
        org_name="Acme",
    )
    assert subject_weekly == "Weekly"
    assert isinstance(html_weekly, str)
    assert len(html_weekly) > 0
