from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.compliance.services.digest_service import DigestService
from app.models.compliance_deadline import ComplianceDeadline
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user


def _fake_provider_chain(self, *, org_id, messages, failure_context):  # noqa: ANN001
    return ("Stub daily narrative for polish coverage.", "groq", False)


def test_ranked_events_escalate_task_priority_by_days_overdue():
    service = DigestService(db=None)  # helper methods only, no DB access needed
    overdue_tasks = [
        {"title": "Barely overdue", "days_overdue": 1},
        {"title": "Overdue a while", "days_overdue": 5},
        {"title": "Severely overdue", "days_overdue": 20},
    ]
    ranked = service._ranked_event_items(
        overdue_tasks=overdue_tasks,
        open_risks=[],
        upcoming_deadlines=[],
        expiring_evidence=[],
    )
    by_title = {item["title"]: item for item in ranked}
    assert by_title["Severely overdue"]["priority_rank"] < by_title["Overdue a while"]["priority_rank"]
    assert by_title["Overdue a while"]["priority_rank"] < by_title["Barely overdue"]["priority_rank"] or (
        by_title["Overdue a while"]["priority_rank"] == by_title["Barely overdue"]["priority_rank"]
        and by_title["Overdue a while"]["urgency_score"] > by_title["Barely overdue"]["urgency_score"]
    )
    # Most urgent item must sort first overall.
    assert ranked[0]["title"] == "Severely overdue"


def test_ranked_events_escalate_deadline_priority_by_days_remaining():
    service = DigestService(db=None)
    deadlines = [
        {"title": "Due today", "days_remaining": 0},
        {"title": "Due next month", "days_remaining": 25},
    ]
    ranked = service._ranked_event_items(
        overdue_tasks=[],
        open_risks=[],
        upcoming_deadlines=deadlines,
        expiring_evidence=[],
    )
    assert ranked[0]["title"] == "Due today"
    by_title = {item["title"]: item for item in ranked}
    assert by_title["Due today"]["priority_rank"] < by_title["Due next month"]["priority_rank"]


def test_daily_digest_reports_total_signal_count_and_truncation(client, db_session, monkeypatch):
    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="ux3-polish-truncate")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    now = datetime.now(UTC)

    # 10 overdue tasks + 10 deadlines exceeds the top-10 digest window, so the digest must
    # report the true total and flag that some signals were not shown, not silently drop them.
    for idx in range(10):
        db_session.add(
            Task(
                organization_id=org_id,
                title=f"Overdue task {idx}",
                description="x",
                status="open",
                priority="high",
                task_type="general",
                owner_user_id=user_id,
                created_by_user_id=user_id,
                due_date=now - timedelta(days=idx + 1),
                metadata_json={},
            )
        )
    for idx in range(10):
        db_session.add(
            ComplianceDeadline(
                organization_id=org_id,
                title=f"Deadline {idx}",
                description="x",
                deadline_type="obligation",
                due_date=(now + timedelta(days=idx + 1)).date(),
                status="pending",
                priority="high",
                owner_user_id=user_id,
                reminder_days_before=3,
                created_by_user_id=user_id,
                tags_json={},
                notes=None,
            )
        )
    db_session.commit()

    service = DigestService(db_session)
    content = service._with_digest_narrative(
        org_id=org_id,
        user_id=user_id,
        payload=service.build_daily_digest(org_id, user_id, db_session),
    )
    assert content["total_signal_count"] == 20
    assert len(content["prioritized_events"]) == 10
    assert content["items_truncated"] is True
    assert content["critical_items_count"] >= 1


def test_daily_digest_not_truncated_when_signal_count_within_window(client, db_session, monkeypatch):
    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="ux3-polish-notruncate")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    now = datetime.now(UTC)

    db_session.add(
        Task(
            organization_id=org_id,
            title="One overdue task",
            description="x",
            status="open",
            priority="high",
            task_type="general",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            due_date=now - timedelta(days=1),
            metadata_json={},
        )
    )
    db_session.commit()

    service = DigestService(db_session)
    content = service._with_digest_narrative(
        org_id=org_id,
        user_id=user_id,
        payload=service.build_daily_digest(org_id, user_id, db_session),
    )
    assert content["total_signal_count"] == 1
    assert content["items_truncated"] is False


def test_daily_digest_endpoint_via_preview_reflects_escalated_ranking(client, db_session, monkeypatch):
    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="ux3-polish-http")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}
    now = datetime.now(UTC)

    db_session.add(
        Task(
            organization_id=org_id,
            title="Long overdue critical task",
            description="x",
            status="open",
            priority="high",
            task_type="general",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            due_date=now - timedelta(days=30),
            metadata_json={},
        )
    )
    db_session.add(
        Task(
            organization_id=org_id,
            title="Just overdue task",
            description="x",
            status="open",
            priority="high",
            task_type="general",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            due_date=now - timedelta(days=1),
            metadata_json={},
        )
    )
    db_session.commit()

    response = client.get("/api/v1/preferences/digest/preview/daily", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    titles_in_order = [item["title"] for item in body["prioritized_events"]]
    assert titles_in_order.index("Long overdue critical task") < titles_in_order.index("Just overdue task")
    assert body["critical_items_count"] >= 1
