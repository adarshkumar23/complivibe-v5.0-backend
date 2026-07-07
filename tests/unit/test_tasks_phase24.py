import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


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


def _create_risk(client, token: str, org_id: str, title: str = "Task Risk") -> str:
    resp = client.post(
        "/api/v1/risks",
        headers=_headers(token, org_id),
        json={"title": title, "category": "operational", "likelihood": 3, "impact": 3},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_control(client, token: str, org_id: str, title: str = "Task Control") -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_evidence(client, token: str, org_id: str, title: str = "Task Evidence") -> str:
    resp = client.post(
        "/api/v1/evidence",
        headers=_headers(token, org_id),
        json={"title": title, "evidence_type": "attestation"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_task_create_permissions_tenant_scope_and_link_validation(client, db_session):
    owner1 = _register(client, "p24-owner1@example.com", "Pass1234!@", "P24 Org1")
    owner2 = _register(client, "p24-owner2@example.com", "Pass1234!@", "P24 Org2")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    cm = _create_active_user_with_role(db_session, org1, "p24-cm@example.com", "compliance_manager")
    readonly = _create_active_user_with_role(db_session, org1, "p24-ro@example.com", "readonly")
    auditor = _create_active_user_with_role(db_session, org1, "p24-au@example.com", "auditor")

    cm_token = _login(client, cm.email, "Pass1234!@")
    ro_token = _login(client, readonly.email, "Pass1234!@")
    au_token = _login(client, auditor.email, "Pass1234!@")

    risk1 = _create_risk(client, owner1, org1, "Risk Org1")
    risk2 = _create_risk(client, owner2, org2, "Risk Org2")

    create_owner = client.post(
        "/api/v1/tasks",
        headers=_headers(owner1, org1),
        json={"title": "Owner task", "linked_entity_type": "risk", "linked_entity_id": risk1},
    )
    assert create_owner.status_code == 201

    create_cm = client.post(
        "/api/v1/tasks",
        headers=_headers(cm_token, org1),
        json={"title": "CM task", "task_type": "risk_treatment", "linked_entity_type": "risk", "linked_entity_id": risk1},
    )
    assert create_cm.status_code == 201

    create_ro = client.post("/api/v1/tasks", headers=_headers(ro_token, org1), json={"title": "RO task"})
    assert create_ro.status_code == 403

    create_au = client.post("/api/v1/tasks", headers=_headers(au_token, org1), json={"title": "AU task"})
    assert create_au.status_code == 403

    cross_link = client.post(
        "/api/v1/tasks",
        headers=_headers(owner1, org1),
        json={"title": "Cross link", "linked_entity_type": "risk", "linked_entity_id": risk2},
    )
    assert cross_link.status_code == 404

    list1 = client.get("/api/v1/tasks", headers=_headers(owner1, org1))
    list2 = client.get("/api/v1/tasks", headers=_headers(owner2, org2))
    assert list1.status_code == 200
    assert list2.status_code == 200
    assert len(list1.json()) >= 2
    assert list2.json() == []


def test_task_owner_validation_update_complete_cancel_notify_and_audit(client, db_session):
    owner1 = _register(client, "p24-owner3@example.com", "Pass1234!@", "P24 Org3")
    owner2 = _register(client, "p24-owner4@example.com", "Pass1234!@", "P24 Org4")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    assignee = _create_active_user_with_role(db_session, org1, "p24-assignee@example.com", "admin")
    other_org_user = _create_active_user_with_role(db_session, org2, "p24-other@example.com", "admin")

    risk1 = _create_risk(client, owner1, org1)
    control1 = _create_control(client, owner1, org1)
    evidence1 = _create_evidence(client, owner1, org1)

    bad_owner = client.post(
        "/api/v1/tasks",
        headers=_headers(owner1, org1),
        json={"title": "Bad owner", "owner_user_id": str(other_org_user.id)},
    )
    assert bad_owner.status_code == 400

    created = client.post(
        "/api/v1/tasks",
        headers=_headers(owner1, org1),
        json={
            "title": "Remediate risk",
            "owner_user_id": str(assignee.id),
            "linked_entity_type": "risk",
            "linked_entity_id": risk1,
            "due_date": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "notify_assignee": True,
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    # outbox queued, no real send
    outbox = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org1)).all()
    assert len(outbox) >= 1
    assert all(item.status == "pending" and item.sent_at is None for item in outbox)

    detail = client.get(f"/api/v1/tasks/{task_id}", headers=_headers(owner1, org1))
    assert detail.status_code == 200
    assert detail.json()["linked_entity_summary"]["entity_type"] == "risk"

    upd = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=_headers(owner1, org1),
        json={"status": "in_progress", "priority": "high"},
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "in_progress"

    completed = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=_headers(owner1, org1),
        json={"completion_notes": "done"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    cancelled_wo_reason = client.post(f"/api/v1/tasks/{task_id}/cancel", headers=_headers(owner1, org1), json={})
    assert cancelled_wo_reason.status_code == 422

    cancelled = client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers=_headers(owner1, org1),
        json={"cancellation_reason": "superseded"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    notify = client.post(f"/api/v1/tasks/{task_id}/notify", headers=_headers(owner1, org1))
    assert notify.status_code == 200

    # linked_entity validation for control/evidence
    linked_control = client.post(
        "/api/v1/tasks",
        headers=_headers(owner1, org1),
        json={"title": "Control task", "linked_entity_type": "control", "linked_entity_id": control1},
    )
    assert linked_control.status_code == 201

    linked_evidence = client.post(
        "/api/v1/tasks",
        headers=_headers(owner1, org1),
        json={"title": "Evidence task", "linked_entity_type": "evidence", "linked_entity_id": evidence1},
    )
    assert linked_evidence.status_code == 201

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1)).json()
    actions = [item["action"] for item in logs]
    assert "task.created" in actions
    assert "task.updated" in actions
    assert "task.completed" in actions
    assert "task.cancelled" in actions
    assert "task.notification_queued" in actions


def test_task_read_surfaces_overdue_flag_and_hours(client):
    owner = _register(client, "p24-owner6@example.com", "Pass1234!@", "P24 Org6")
    org_id = _org_id(client, owner)

    overdue = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org_id),
        json={"title": "Overdue", "due_date": (datetime.now(UTC) - timedelta(hours=5)).isoformat()},
    )
    assert overdue.status_code == 201
    body = overdue.json()
    assert body["is_overdue"] is True
    assert body["overdue_by_hours"] >= 4.9

    on_time = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org_id),
        json={"title": "Not due yet", "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert on_time.status_code == 201
    assert on_time.json()["is_overdue"] is False
    assert on_time.json()["overdue_by_hours"] is None

    # A completed task with a due date in the past is no longer "overdue" --
    # it's done.
    complete = client.post(f"/api/v1/tasks/{overdue.json()['id']}/complete", headers=_headers(owner, org_id), json={})
    assert complete.status_code == 200
    assert complete.json()["is_overdue"] is False


def test_task_double_complete_and_double_cancel_race_return_409(client):
    owner = _register(client, "p24-owner7@example.com", "Pass1234!@", "P24 Org7")
    org_id = _org_id(client, owner)

    created = client.post("/api/v1/tasks", headers=_headers(owner, org_id), json={"title": "Race target"})
    task_id = created.json()["id"]

    first_complete = client.post(f"/api/v1/tasks/{task_id}/complete", headers=_headers(owner, org_id), json={})
    assert first_complete.status_code == 200
    second_complete = client.post(f"/api/v1/tasks/{task_id}/complete", headers=_headers(owner, org_id), json={})
    assert second_complete.status_code == 409

    other_created = client.post("/api/v1/tasks", headers=_headers(owner, org_id), json={"title": "Cancel race target"})
    other_task_id = other_created.json()["id"]
    first_cancel = client.post(
        f"/api/v1/tasks/{other_task_id}/cancel",
        headers=_headers(owner, org_id),
        json={"cancellation_reason": "no longer needed"},
    )
    assert first_cancel.status_code == 200
    second_cancel = client.post(
        f"/api/v1/tasks/{other_task_id}/cancel",
        headers=_headers(owner, org_id),
        json={"cancellation_reason": "no longer needed"},
    )
    assert second_cancel.status_code == 409

    # Existing behavior: cancelling an already-completed task is still a
    # valid transition (not a race, an intentional undo), so this must NOT
    # be blocked by the terminal-state guard above.
    completed_task = client.post("/api/v1/tasks", headers=_headers(owner, org_id), json={"title": "Complete then cancel"})
    completed_task_id = completed_task.json()["id"]
    client.post(f"/api/v1/tasks/{completed_task_id}/complete", headers=_headers(owner, org_id), json={})
    cancel_after_complete = client.post(
        f"/api/v1/tasks/{completed_task_id}/cancel",
        headers=_headers(owner, org_id),
        json={"cancellation_reason": "superseded"},
    )
    assert cancel_after_complete.status_code == 200


def test_task_detail_flags_linked_risk_as_stale_when_already_resolved(client):
    owner = _register(client, "p24-owner8@example.com", "Pass1234!@", "P24 Org8")
    org_id = _org_id(client, owner)
    risk_id = _create_risk(client, owner, org_id, "Stale link risk")

    task = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org_id),
        json={"title": "Treat risk", "linked_entity_type": "risk", "linked_entity_id": risk_id},
    )
    task_id = task.json()["id"]

    fresh_detail = client.get(f"/api/v1/tasks/{task_id}", headers=_headers(owner, org_id))
    assert fresh_detail.status_code == 200
    assert fresh_detail.json()["linked_entity_stale"] is False

    # Risk gets resolved through its own workflow while the task is still open.
    risk_update = client.patch(f"/api/v1/risks/{risk_id}", headers=_headers(owner, org_id), json={"status": "mitigated"})
    assert risk_update.status_code == 200

    stale_detail = client.get(f"/api/v1/tasks/{task_id}", headers=_headers(owner, org_id))
    assert stale_detail.status_code == 200
    assert stale_detail.json()["linked_entity_stale"] is True

    # Once the task itself is completed, staleness of the (now moot) link no
    # longer matters.
    client.post(f"/api/v1/tasks/{task_id}/complete", headers=_headers(owner, org_id), json={})
    completed_detail = client.get(f"/api/v1/tasks/{task_id}", headers=_headers(owner, org_id))
    assert completed_detail.json()["linked_entity_stale"] is False


def test_risk_treatment_task_and_reminders_and_summary(client, db_session):
    owner = _register(client, "p24-owner5@example.com", "Pass1234!@", "P24 Org5")
    org_id = _org_id(client, owner)

    risk_owner = _create_active_user_with_role(db_session, org_id, "p24-risk-owner@example.com", "admin")
    risk_id = _create_risk(client, owner, org_id, "Risk treatment target")

    # set risk owner so treatment task defaults correctly
    risk_update = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=_headers(owner, org_id),
        json={"owner_user_id": str(risk_owner.id)},
    )
    assert risk_update.status_code == 200

    treatment = client.post(
        f"/api/v1/risks/{risk_id}/treatment-task",
        headers=_headers(owner, org_id),
        json={"priority": "urgent", "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat(), "notify_assignee": True},
    )
    assert treatment.status_code == 201
    task = treatment.json()
    assert task["task_type"] == "risk_treatment"
    assert task["linked_entity_type"] == "risk"
    assert task["linked_entity_id"] == risk_id
    assert task["owner_user_id"] == str(risk_owner.id)

    # create overdue and due-soon tasks for reminders/summary
    overdue = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org_id),
        json={
            "title": "Overdue task",
            "owner_user_id": str(risk_owner.id),
            "due_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "status": "open",
        },
    )
    assert overdue.status_code == 201

    due_soon = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org_id),
        json={
            "title": "Soon task",
            "owner_user_id": str(risk_owner.id),
            "due_date": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    assert due_soon.status_code == 201

    reminder_resp = client.post(
        "/api/v1/tasks/reminders/queue",
        headers=_headers(owner, org_id),
        json={"due_within_days": 3, "overdue_only": False, "limit": 50},
    )
    assert reminder_resp.status_code == 200
    assert reminder_resp.json()["queued_count"] >= 1

    summary = client.get("/api/v1/tasks/summary", headers=_headers(owner, org_id))
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_tasks"] >= 3
    assert body["overdue_tasks"] >= 1
    assert body["due_soon_tasks"] >= 1
    assert body["urgent_open_tasks"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id)).json()
    actions = [item["action"] for item in logs]
    assert "risk.treatment_task_created" in actions
    assert "task.reminders_queued" in actions
