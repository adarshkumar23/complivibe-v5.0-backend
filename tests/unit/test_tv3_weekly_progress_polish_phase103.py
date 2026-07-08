from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.compliance.services.digest_service import DigestService
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user


def _fake_provider_chain(self, *, org_id, messages, failure_context):  # noqa: ANN001
    return ("Stub narrative for polish coverage.", "groq", False)


def test_weekly_digest_flags_insufficient_history_for_new_org(client, db_session, monkeypatch):
    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="tv3-polish-new-org")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    # Org was just created (bootstrap_org_user does not backdate created_at), so it is
    # younger than the 14-day comparison window used for week-over-week metrics.
    digest = DigestService(db_session).build_weekly_digest(org_id, user_id, db_session)
    assert "insufficient_history_for_comparison" in digest["data_staleness_flags"]
    assert digest["score_delta_meaningful"] is False
    assert digest["top_3_wins"] == ["Not enough account history yet for a week-over-week comparison."]


def test_weekly_digest_does_not_flag_insufficient_history_for_established_org(client, db_session, monkeypatch):
    from app.models.organization import Organization

    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="tv3-polish-old-org")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    org_row = db_session.get(Organization, org_id)
    org_row.created_at = datetime.now(UTC) - timedelta(days=60)
    db_session.commit()

    digest = DigestService(db_session).build_weekly_digest(org_id, user_id, db_session)
    assert "insufficient_history_for_comparison" not in digest["data_staleness_flags"]
    assert digest["score_delta_meaningful"] is True


def test_preview_weekly_digest_endpoint_returns_content_without_sending(client, db_session, monkeypatch):
    from app.models.organization import Organization

    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="tv3-polish-preview")
    org_id = uuid.UUID(ctx["organization_id"])
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    org_row = db_session.get(Organization, org_id)
    org_row.created_at = datetime.now(UTC) - timedelta(days=60)
    db_session.add(
        Task(
            organization_id=org_id,
            title="Preview completed task",
            description="x",
            status="completed",
            priority="normal",
            task_type="general",
            owner_user_id=uuid.UUID(ctx["user_id"]),
            created_by_user_id=uuid.UUID(ctx["user_id"]),
            due_date=datetime.now(UTC) - timedelta(days=1),
            completed_at=datetime.now(UTC) - timedelta(days=1),
            metadata_json={},
        )
    )
    db_session.commit()

    response = client.get("/api/v1/preferences/digest/preview/weekly", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["digest_type"] == "weekly"
    assert "narrative_paragraph" in body
    assert "top_3_wins" in body

    from app.models.email_outbox import EmailOutbox

    outbox_count = (
        db_session.query(EmailOutbox)
        .filter(EmailOutbox.organization_id == org_id, EmailOutbox.event_type == "digest.weekly")
        .count()
    )
    assert outbox_count == 0, "preview must not queue an email"


def test_preview_daily_digest_endpoint_returns_content(client, monkeypatch):
    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)
    ctx = bootstrap_org_user(client, email_prefix="tv3-polish-preview-daily")
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    response = client.get("/api/v1/preferences/digest/preview/daily", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["digest_type"] == "daily"
    assert "prioritized_events" in body


def test_preview_digest_rejects_invalid_digest_type(client):
    ctx = bootstrap_org_user(client, email_prefix="tv3-polish-preview-bad")
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    response = client.get("/api/v1/preferences/digest/preview/monthly", headers=headers)
    assert response.status_code in {404, 422}
