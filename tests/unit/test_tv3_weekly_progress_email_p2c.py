from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.compliance.services.digest_service import DigestService
from app.models.compliance_deadline import ComplianceDeadline
from app.models.email_outbox import EmailOutbox
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.org_email_config import OrgEmailConfig
from app.models.task import Task
from app.models.user_notification_preference import UserNotificationPreference
from tests.helpers.auth_org import bootstrap_org_user


def test_tv3_weekly_progress_computes_delta_wins_priorities(client, db_session, monkeypatch):
    ctx = bootstrap_org_user(client, email_prefix="tv3-weekly")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    now = datetime.now(UTC)

    def _fake_provider_chain(self, *, org_id, messages, failure_context):  # noqa: ANN001
        return ("Weekly progress improved through higher completion velocity while controlling net issue intake.", "groq", False)

    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)

    # Previous week baseline: lower completions and higher issue intake.
    prev_start = now - timedelta(days=14)
    prev_mid = prev_start + timedelta(days=2)
    db_session.add(
        Task(
            organization_id=org_id,
            title="Prev week completed task",
            description="x",
            status="completed",
            priority="normal",
            task_type="general",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            due_date=prev_mid,
            completed_at=prev_mid,
            metadata_json={},
        )
    )
    for idx in range(3):
        db_session.add(
            Issue(
                organization_id=org_id,
                title=f"Prev week issue {idx}",
                description="desc",
                issue_type="custom",
                severity="high",
                source_type="manual",
                status="open",
                owner_id=user_id,
                assigned_to=user_id,
                created_by=user_id,
                created_at=prev_mid + timedelta(hours=idx),
                deleted_at=None,
            )
        )

    # Current week: more completions, fewer new issues, more evidence/deadline closure.
    cur_start = now - timedelta(days=7)
    cur_mid = cur_start + timedelta(days=2)
    for idx in range(4):
        completed_at = cur_mid + timedelta(hours=idx)
        db_session.add(
            Task(
                organization_id=org_id,
                title=f"Current week completed task {idx}",
                description="x",
                status="completed",
                priority="normal",
                task_type="general",
                owner_user_id=user_id,
                created_by_user_id=user_id,
                due_date=completed_at,
                completed_at=completed_at,
                metadata_json={},
            )
        )

    db_session.add(
        Issue(
            organization_id=org_id,
            title="Current week issue",
            description="desc",
            issue_type="custom",
            severity="medium",
            source_type="manual",
            status="open",
            owner_id=user_id,
            assigned_to=user_id,
            created_by=user_id,
            created_at=cur_mid,
            deleted_at=None,
        )
    )
    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Reviewed evidence",
            description="x",
            evidence_type="document",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="fresh",
            reviewed_at=cur_mid,
            metadata_json={},
        )
    )
    db_session.add(
        ComplianceDeadline(
            organization_id=org_id,
            title="Closed deadline",
            description="x",
            deadline_type="obligation",
            due_date=cur_mid.date(),
            status="completed",
            priority="high",
            owner_user_id=user_id,
            reminder_days_before=3,
            created_by_user_id=user_id,
            completed_at=cur_mid,
            tags_json={},
            notes=None,
        )
    )
    db_session.commit()

    digest = DigestService(db_session).build_weekly_digest(org_id, user_id, db_session)
    assert digest["digest_type"] == "weekly"
    assert isinstance(digest["score_delta"], int)
    assert digest["score_delta"] > 0
    assert len(digest["top_3_wins"]) == 3
    assert len(digest["top_3_priorities"]) >= 1
    assert digest["weekly_metrics_current"]["tasks_completed"] > digest["weekly_metrics_previous"]["tasks_completed"]
    assert digest["weekly_metrics_current"]["issues_opened"] < digest["weekly_metrics_previous"]["issues_opened"]
    assert digest["narrative_source"] in {"ai_groq", "ai_azure", "deterministic_fallback"}


def test_tv3_weekly_send_queues_ai_narrative_payload(client, db_session, monkeypatch):
    ctx = bootstrap_org_user(client, email_prefix="tv3-weekly-send")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    now = datetime.now(UTC)

    def _fake_provider_chain(self, *, org_id, messages, failure_context):  # noqa: ANN001
        return ("This week showed stronger closure rates and a tighter backlog trajectory; keep focus on issue intake control.", "groq", False)

    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)

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
    db_session.add(
        UserNotificationPreference(
            organization_id=org_id,
            user_id=user_id,
            notification_type="digest_weekly",
            channel="email",
            min_severity=None,
            is_enabled=True,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        Task(
            organization_id=org_id,
            title="Current completion",
            description="x",
            status="completed",
            priority="normal",
            task_type="general",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            due_date=now - timedelta(days=1),
            completed_at=now - timedelta(days=1),
            metadata_json={},
        )
    )
    db_session.commit()

    sent = DigestService(db_session).send_digest(org_id, user_id, "weekly", db_session)
    assert sent is True

    outbox = (
        db_session.query(EmailOutbox)
        .filter(
            EmailOutbox.organization_id == org_id,
            EmailOutbox.event_type == "digest.weekly",
        )
        .order_by(EmailOutbox.queued_at.desc())
        .first()
    )
    assert outbox is not None
    context = outbox.template_context or {}
    assert context.get("digest_type") == "weekly"
    assert isinstance(context.get("score_delta"), int)
    assert isinstance(context.get("top_3_wins"), list)
    assert isinstance(context.get("top_3_priorities"), list)
    assert context.get("narrative_source") in {"ai_groq", "ai_azure", "deterministic_fallback"}
