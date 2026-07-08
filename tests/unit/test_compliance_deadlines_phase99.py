from datetime import date, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.compliance_deadline_event import ComplianceDeadlineEvent
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/deadlines"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _create_deadline(
    client,
    headers: dict[str, str],
    *,
    owner_user_id: str,
    title: str,
    due_date_value: date,
    deadline_type: str = "custom",
    priority: str = "medium",
    reminder_days_before: int = 7,
    linked_entity_type: str | None = None,
    linked_entity_id: str | None = None,
) -> dict:
    payload = {
        "title": title,
        "deadline_type": deadline_type,
        "due_date": due_date_value.isoformat(),
        "priority": priority,
        "owner_user_id": owner_user_id,
        "reminder_days_before": reminder_days_before,
    }
    if linked_entity_type is not None:
        payload["linked_entity_type"] = linked_entity_type
    if linked_entity_id is not None:
        payload["linked_entity_id"] = linked_entity_id

    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase99_deadline_crud_terminal_states_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p99-crud-a")
    org2 = bootstrap_org_user(client, email_prefix="p99-crud-b")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "p99-owner1@example.com", "admin")
    _ = _create_active_user_with_role(db_session, org2["organization_id"], "p99-owner2@example.com", "admin")

    deadline = _create_deadline(
        client,
        org1["org_headers"],
        owner_user_id=str(owner1.id),
        title="Policy Review",
        due_date_value=date.today() + timedelta(days=5),
        deadline_type="policy_review",
    )

    listed = client.get(BASE, headers=org1["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.patch(
        f"{BASE}/{deadline['id']}",
        headers=org1["org_headers"],
        json={"priority": "high", "notes": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == "high"

    completed = client.post(
        f"{BASE}/{deadline['id']}/complete",
        headers=org1["org_headers"],
        json={"completion_notes": "done"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    blocked_patch = client.patch(
        f"{BASE}/{deadline['id']}",
        headers=org1["org_headers"],
        json={"priority": "low"},
    )
    assert blocked_patch.status_code == 400

    blocked_cancel = client.post(
        f"{BASE}/{deadline['id']}/cancel",
        headers=org1["org_headers"],
        json={"cancellation_reason": "should fail"},
    )
    assert blocked_cancel.status_code == 400

    cross_org = client.get(f"{BASE}/{deadline['id']}", headers=org2["org_headers"])
    assert cross_org.status_code == 404


def test_phase99_overdue_detection_and_reminder_window(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p99-eval")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p99-eval-owner@example.com", "admin")

    overdue_deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Overdue Deadline",
        due_date_value=date.today() - timedelta(days=1),
        deadline_type="audit_preparation",
        reminder_days_before=7,
    )
    reminder_deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Reminder Deadline",
        due_date_value=date.today() + timedelta(days=2),
        deadline_type="control_review",
        reminder_days_before=3,
    )

    evaluated = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": False})
    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["overdue_marked"] >= 1
    assert body["reminders_triggered"] >= 1
    assert body["events_created"] >= 2

    overdue_detail = client.get(f"{BASE}/{overdue_deadline['id']}", headers=org["org_headers"])
    assert overdue_detail.status_code == 200
    assert overdue_detail.json()["status"] == "overdue"

    events = client.get(f"{BASE}/events", headers=org["org_headers"])
    assert events.status_code == 200
    event_types = [row["event_type"] for row in events.json()]
    assert "overdue_detected" in event_types
    assert "reminder_due" in event_types

    _ = reminder_deadline


def test_phase99_dry_run_vs_live_and_idempotent_event_creation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p99-drylive")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p99-drylive-owner@example.com", "admin")

    dry_deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Dry Deadline",
        due_date_value=date.today() + timedelta(days=1),
        reminder_days_before=2,
    )

    outbox_before = db_session.query(EmailOutbox).count()

    dry = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["events_created"] >= 1

    dry_events = client.get(f"{BASE}/events?deadline_id={dry_deadline['id']}&event_type=reminder_due", headers=org["org_headers"])
    assert dry_events.status_code == 200
    assert len(dry_events.json()) >= 1
    assert all(evt["dry_run"] is True for evt in dry_events.json())
    assert all(evt["outbox_queued"] is False for evt in dry_events.json())

    assert db_session.query(EmailOutbox).count() == outbox_before

    live_deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Live Deadline",
        due_date_value=date.today() + timedelta(days=1),
        reminder_days_before=2,
    )

    first_live = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": False})
    assert first_live.status_code == 200

    first_event_count = db_session.query(ComplianceDeadlineEvent).filter(
        ComplianceDeadlineEvent.organization_id == uuid.UUID(org["organization_id"]),
        ComplianceDeadlineEvent.deadline_id == uuid.UUID(live_deadline["id"]),
        ComplianceDeadlineEvent.event_type == "reminder_due",
    ).count()

    second_live = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": False})
    assert second_live.status_code == 200

    second_event_count = db_session.query(ComplianceDeadlineEvent).filter(
        ComplianceDeadlineEvent.organization_id == uuid.UUID(org["organization_id"]),
        ComplianceDeadlineEvent.deadline_id == uuid.UUID(live_deadline["id"]),
        ComplianceDeadlineEvent.event_type == "reminder_due",
    ).count()
    assert second_event_count == first_event_count


def test_phase99_linked_entity_type_validation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p99-link-a")
    org2 = bootstrap_org_user(client, email_prefix="p99-link-b")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "p99-link-owner1@example.com", "admin")
    _ = _create_active_user_with_role(db_session, org2["organization_id"], "p99-link-owner2@example.com", "admin")

    control1 = _create_control(client, org1["org_headers"], title="Link Control 1")
    control2 = _create_control(client, org2["org_headers"], title="Link Control 2")

    ok = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "title": "Linked OK",
            "deadline_type": "control_review",
            "due_date": (date.today() + timedelta(days=10)).isoformat(),
            "priority": "medium",
            "owner_user_id": str(owner1.id),
            "linked_entity_type": "control",
            "linked_entity_id": control1["id"],
        },
    )
    assert ok.status_code == 201

    cross = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "title": "Linked Cross",
            "deadline_type": "control_review",
            "due_date": (date.today() + timedelta(days=10)).isoformat(),
            "priority": "medium",
            "owner_user_id": str(owner1.id),
            "linked_entity_type": "control",
            "linked_entity_id": control2["id"],
        },
    )
    assert cross.status_code == 404


def test_phase99_summary_metrics_and_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p99-summary")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p99-summary-owner@example.com", "admin")

    d1 = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Complete me",
        due_date_value=date.today() + timedelta(days=3),
        deadline_type="framework_review",
        priority="critical",
    )
    d2 = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Waive me",
        due_date_value=date.today() + timedelta(days=4),
        deadline_type="policy_review",
        priority="high",
    )
    d3 = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Cancel me",
        due_date_value=date.today() + timedelta(days=5),
        deadline_type="vendor_assessment",
        priority="low",
    )

    comp = client.post(f"{BASE}/{d1['id']}/complete", headers=org["org_headers"], json={"completion_notes": "done"})
    assert comp.status_code == 200
    waive = client.post(f"{BASE}/{d2['id']}/waive", headers=org["org_headers"], json={"waiver_reason": "accepted"})
    assert waive.status_code == 200
    cancel = client.post(f"{BASE}/{d3['id']}/cancel", headers=org["org_headers"], json={"cancellation_reason": "obsolete"})
    assert cancel.status_code == 200

    eval_resp = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": True})
    assert eval_resp.status_code == 200

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_deadlines"] == 3
    assert body["completed_deadlines"] == 1
    assert body["waived_deadlines"] == 1
    assert body["cancelled_deadlines"] == 1
    assert body["by_priority"]["critical"] == 1
    assert body["by_priority"]["high"] == 1
    assert body["by_priority"]["low"] == 1
    assert "high_risk_overdue_count" in body
    assert "stale_status_count" in body
    assert "deadlines_without_active_owner" in body

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "compliance_deadline.created" in actions
    assert "compliance_deadline.completed" in actions
    assert "compliance_deadline.waived" in actions
    assert "compliance_deadline.cancelled" in actions
    assert "compliance_deadline.evaluated" in actions


def test_phase99_overdue_only_includes_stale_upcoming_and_emits_context_flags(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p99-stale-list")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p99-stale-owner@example.com", "admin")

    stale_deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Stale Upcoming",
        due_date_value=date.today() - timedelta(days=2),
        deadline_type="custom",
        priority="high",
    )

    overdue_only = client.get(f"{BASE}?overdue_only=true", headers=org["org_headers"])
    assert overdue_only.status_code == 200
    rows = overdue_only.json()
    assert any(row["id"] == stale_deadline["id"] for row in rows)
    stale_row = next(row for row in rows if row["id"] == stale_deadline["id"])
    assert stale_row["is_status_stale"] is True
    assert stale_row["recommended_status"] == "overdue"
    assert "past_due_not_marked_overdue" in stale_row["context_flags"]


def test_g9_evaluate_due_defaults_to_real_run_not_dry_run(client, db_session):
    """G9 item 8a: evaluate-due is an action-verb endpoint -- omitting dry_run must
    actually evaluate for real (mark overdue, queue reminders), not silently preview."""
    org = bootstrap_org_user(client, email_prefix="p99-default-live")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p99-default-owner@example.com", "admin")

    deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Default Call Deadline",
        due_date_value=date.today() - timedelta(days=1),
    )

    response = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={})
    assert response.status_code == 200

    refreshed = client.get(f"{BASE}/{deadline['id']}", headers=org["org_headers"])
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "overdue"

    events = client.get(f"{BASE}/events?deadline_id={deadline['id']}", headers=org["org_headers"])
    assert events.status_code == 200
    assert any(evt["dry_run"] is False for evt in events.json())


def test_g9_dry_run_never_poisons_a_subsequent_real_evaluate_due(client, db_session):
    """G9 item 8b: a dry-run pass must have zero persistent side effects -- it must
    never make a later real pass on the same day believe the deadline was already
    handled."""
    org = bootstrap_org_user(client, email_prefix="p99-dry-poison")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p99-dry-poison-owner@example.com", "admin")

    deadline = _create_deadline(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        title="Poison Test Deadline",
        due_date_value=date.today() - timedelta(days=1),
    )

    dry = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["overdue_marked"] >= 1

    # Deadline must still be "upcoming" in the DB -- dry run must not mutate state.
    still_upcoming = client.get(f"{BASE}/{deadline['id']}", headers=org["org_headers"])
    assert still_upcoming.json()["status"] == "upcoming"

    # A REAL pass later the same day must still mark it overdue -- the dry run's
    # event record must not be mistaken for "already handled today".
    real = client.post(f"{BASE}/evaluate-due", headers=org["org_headers"], json={"dry_run": False})
    assert real.status_code == 200
    assert real.json()["overdue_marked"] >= 1
    assert real.json()["events_skipped_duplicates"] == 0

    now_overdue = client.get(f"{BASE}/{deadline['id']}", headers=org["org_headers"])
    assert now_overdue.json()["status"] == "overdue"

    events = client.get(f"{BASE}/events?deadline_id={deadline['id']}&event_type=overdue_detected", headers=org["org_headers"])
    assert events.status_code == 200
    real_events = [evt for evt in events.json() if evt["dry_run"] is False]
    assert len(real_events) == 1
