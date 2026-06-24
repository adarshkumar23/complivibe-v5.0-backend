import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_system_governance_review_event import AISystemGovernanceReviewEvent
from app.models.email_outbox import EmailOutbox
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Scheduled AI") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "ai_feature"},
    )
    assert response.status_code == 201
    return response.json()


def _create_review(
    client,
    headers: dict[str, str],
    ai_system_id: str,
    *,
    review_type: str = "periodic_review",
    title: str = "Scheduled Review",
    assigned_to_user_id: str | None = None,
) -> dict:
    payload = {"review_type": review_type, "title": title}
    if assigned_to_user_id is not None:
        payload["assigned_to_user_id"] = assigned_to_user_id
    response = client.post(
        f"/api/v1/ai-systems/{ai_system_id}/governance-reviews",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _schedule_review(client, headers: dict[str, str], ai_system_id: str, review_id: str, due_at: datetime, policy_id: str | None = None):
    payload = {"due_at": due_at.isoformat()}
    if policy_id is not None:
        payload["reminder_policy_id"] = policy_id
    return client.post(
        f"/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/schedule",
        headers=headers,
        json=payload,
    )


def test_phase53_set_review_schedule_and_status_constraints(client):
    owner = bootstrap_org_user(client, email_prefix="p53-schedule-owner")
    headers = owner["org_headers"]
    ai_system = _create_ai_system(client, headers)

    review = _create_review(client, headers, ai_system["id"], title="R1")
    due_at = datetime.now(UTC) + timedelta(days=2)
    scheduled = _schedule_review(client, headers, ai_system["id"], review["id"], due_at)
    assert scheduled.status_code == 200
    body = scheduled.json()
    assert body["due_at"] is not None
    assert body["status"] == "pending"

    completed = _create_review(client, headers, ai_system["id"], title="R2")
    complete_resp = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{completed['id']}/complete",
        headers=headers,
        json={"outcome": "approved"},
    )
    assert complete_resp.status_code == 200

    cannot_schedule_completed = _schedule_review(
        client,
        headers,
        ai_system["id"],
        completed["id"],
        datetime.now(UTC) + timedelta(days=1),
    )
    assert cannot_schedule_completed.status_code == 400

    cancelled = _create_review(client, headers, ai_system["id"], title="R3")
    cancel_resp = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{cancelled['id']}/cancel",
        headers=headers,
        json={"cancellation_reason": "not needed"},
    )
    assert cancel_resp.status_code == 200

    cannot_schedule_cancelled = _schedule_review(
        client,
        headers,
        ai_system["id"],
        cancelled["id"],
        datetime.now(UTC) + timedelta(days=1),
    )
    assert cannot_schedule_cancelled.status_code == 400


def test_phase53_reminder_policy_crud_and_negative_values_rejected(client):
    owner = bootstrap_org_user(client, email_prefix="p53-policy-owner")
    headers = owner["org_headers"]

    create = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": "Default Policy",
            "review_type": "periodic_review",
            "days_before_due": 2,
            "overdue_after_days": 1,
            "escalation_after_days": 3,
            "notify_assignee": True,
            "status": "active",
        },
    )
    assert create.status_code == 201
    policy_id = create.json()["id"]

    listed = client.get("/api/v1/ai-governance/review-reminder-policies", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == policy_id for row in listed.json())

    updated = client.patch(
        f"/api/v1/ai-governance/review-reminder-policies/{policy_id}",
        headers=headers,
        json={"name": "Updated Policy", "status": "inactive", "days_before_due": 4},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Policy"
    assert updated.json()["status"] == "inactive"
    assert updated.json()["days_before_due"] == 4

    archived = client.post(
        f"/api/v1/ai-governance/review-reminder-policies/{policy_id}/archive",
        headers=headers,
        json={},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    negative_days = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": "Bad",
            "days_before_due": -1,
            "overdue_after_days": 0,
            "escalation_after_days": 0,
        },
    )
    assert negative_days.status_code in {400, 422}


def test_phase53_due_queue_tenant_scope_and_overdue_only(client):
    org1 = bootstrap_org_user(client, email_prefix="p53-queue-org1")
    org2 = bootstrap_org_user(client, email_prefix="p53-queue-org2")

    ai1 = _create_ai_system(client, org1["org_headers"], name="Org1 Queue AI")
    ai2 = _create_ai_system(client, org2["org_headers"], name="Org2 Queue AI")

    review1 = _create_review(client, org1["org_headers"], ai1["id"], title="Org1 due")
    _schedule_review(
        client,
        org1["org_headers"],
        ai1["id"],
        review1["id"],
        datetime.now(UTC) - timedelta(days=1),
    )

    review2 = _create_review(client, org2["org_headers"], ai2["id"], title="Org2 due")
    _schedule_review(
        client,
        org2["org_headers"],
        ai2["id"],
        review2["id"],
        datetime.now(UTC) - timedelta(days=1),
    )

    org1_queue = client.get("/api/v1/ai-governance/review-queue", headers=org1["org_headers"])
    assert org1_queue.status_code == 200
    assert len(org1_queue.json()) == 1
    assert org1_queue.json()[0]["ai_system_id"] == ai1["id"]

    org1_overdue_only = client.get(
        "/api/v1/ai-governance/review-queue?overdue_only=true",
        headers=org1["org_headers"],
    )
    assert org1_overdue_only.status_code == 200
    assert len(org1_overdue_only.json()) == 1
    assert org1_overdue_only.json()[0]["is_overdue"] is True


def test_phase53_evaluate_dry_run_live_idempotent_notify_events_and_summary(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p53-eval-owner")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])
    ai_system = _create_ai_system(client, headers)

    reminder_policy = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": "Reminder policy",
            "review_type": "periodic_review",
            "days_before_due": 2,
            "overdue_after_days": 20,
            "escalation_after_days": 30,
            "notify_assignee": True,
            "status": "active",
        },
    )
    assert reminder_policy.status_code == 201

    overdue_policy = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": "Overdue policy",
            "review_type": "change_review",
            "days_before_due": 0,
            "overdue_after_days": 0,
            "escalation_after_days": 30,
            "notify_assignee": False,
            "status": "active",
        },
    )
    assert overdue_policy.status_code == 201

    escalation_policy = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": "Escalation policy",
            "review_type": "pre_production_review",
            "days_before_due": 0,
            "overdue_after_days": 30,
            "escalation_after_days": 0,
            "notify_assignee": False,
            "status": "active",
        },
    )
    assert escalation_policy.status_code == 201

    r1 = _create_review(
        client,
        headers,
        ai_system["id"],
        review_type="periodic_review",
        title="Reminder Review",
        assigned_to_user_id=owner["user_id"],
    )
    r2 = _create_review(client, headers, ai_system["id"], review_type="change_review", title="Overdue Review")
    r3 = _create_review(client, headers, ai_system["id"], review_type="pre_production_review", title="Escalation Review")

    now = datetime.now(UTC)
    s1 = _schedule_review(
        client,
        headers,
        ai_system["id"],
        r1["id"],
        now + timedelta(days=1),
        reminder_policy.json()["id"],
    )
    s2 = _schedule_review(
        client,
        headers,
        ai_system["id"],
        r2["id"],
        now - timedelta(days=1),
        overdue_policy.json()["id"],
    )
    s3 = _schedule_review(
        client,
        headers,
        ai_system["id"],
        r3["id"],
        now - timedelta(days=1),
        escalation_policy.json()["id"],
    )
    assert s1.status_code == 200
    assert s2.status_code == 200
    assert s3.status_code == 200

    before_events = db_session.query(AISystemGovernanceReviewEvent).filter_by(organization_id=org_id).count()
    dry_run = client.post(
        "/api/v1/ai-governance/review-queue/evaluate-schedules",
        headers=headers,
        json={"dry_run": True, "notify": True},
    )
    assert dry_run.status_code == 200
    dry_body = dry_run.json()
    assert dry_body["dry_run"] is True
    assert dry_body["created_count"] == 0
    assert dry_body["would_create_count"] >= 3
    after_dry_events = db_session.query(AISystemGovernanceReviewEvent).filter_by(organization_id=org_id).count()
    assert after_dry_events == before_events

    live = client.post(
        "/api/v1/ai-governance/review-queue/evaluate-schedules",
        headers=headers,
        json={"dry_run": False, "notify": True},
    )
    assert live.status_code == 200
    live_body = live.json()
    assert live_body["dry_run"] is False
    assert live_body["created_count"] >= 3
    assert live_body["queued_email_count"] >= 1

    events = db_session.query(AISystemGovernanceReviewEvent).filter_by(organization_id=org_id).all()
    event_types = {row.event_type for row in events}
    assert "reminder_due" in event_types
    assert "review_overdue" in event_types
    assert "escalation_due" in event_types

    outbox_rows = (
        db_session.query(EmailOutbox)
        .filter(
            EmailOutbox.organization_id == org_id,
            EmailOutbox.event_type == "ai_system.governance_review.reminder",
        )
        .all()
    )
    assert len(outbox_rows) >= 1
    assert all(row.sent_at is None for row in outbox_rows)

    second_live = client.post(
        "/api/v1/ai-governance/review-queue/evaluate-schedules",
        headers=headers,
        json={"dry_run": False, "notify": True},
    )
    assert second_live.status_code == 200
    assert second_live.json()["created_count"] == 0

    listed = client.get("/api/v1/ai-governance/review-events", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) >= 3

    event_id = listed.json()[0]["id"]
    resolved = client.post(
        f"/api/v1/ai-governance/review-events/{event_id}/resolve",
        headers=headers,
        json={"resolution_notes": "triaged"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    summary = client.get("/api/v1/ai-governance/review-schedule-summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["scheduled_reviews"] >= 3
    assert summary_body["unscheduled_reviews"] >= 0
    assert summary_body["open_events"] >= 0
    assert summary_body["resolved_events"] >= 1
    assert "reminder_due" in summary_body["by_event_type"]

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_review.scheduled" in actions
    assert "ai_system_governance_review_reminder_policy.created" in actions
    assert "ai_system_governance_review_schedule.evaluated" in actions
    assert "ai_system_governance_review_event.resolved" in actions
