import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.role import Role
from app.models.task import Task
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


def _create_rule(client, token: str, org_id: str, trigger_type: str = "scheduled_placeholder") -> str:
    resp = client.post(
        "/api/v1/automation/rules",
        headers=_headers(token, org_id),
        json={
            "name": "Sched Rule",
            "trigger_type": trigger_type,
            "condition_type": "risk_without_owner",
            "action_type": "create_task",
            "status": "active",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_risk_without_owner(client, token: str, org_id: str, title: str = "No owner risk") -> str:
    resp = client.post(
        "/api/v1/risks",
        headers=_headers(token, org_id),
        json={"title": title, "category": "operational", "likelihood": 5, "impact": 4},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_schedule_update_permissions_and_version_snapshot(client, db_session):
    owner = _register(client, "p26-owner1@example.com", "Pass1234!@", "P26 Org1")
    org = _org_id(client, owner)
    readonly = _create_active_user_with_role(db_session, org, "p26-ro@example.com", "readonly")
    ro_token = _login(client, readonly.email, "Pass1234!@")

    rule_id = _create_rule(client, owner, org)

    bad_cadence = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={"schedule_enabled": True, "schedule_cadence": "bad"},
    )
    assert bad_cadence.status_code in {400, 422}

    denied = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(ro_token, org),
        json={"schedule_enabled": True, "schedule_cadence": "daily"},
    )
    assert denied.status_code == 403

    updated = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "daily",
            "schedule_timezone": "UTC",
            "run_mode": "live",
            "version_notes": "enable schedule",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["schedule_enabled"] is True
    assert updated.json()["version"] >= 2
    assert updated.json()["next_run_at"] is not None

    versions = client.get(f"/api/v1/automation/rules/{rule_id}/versions", headers=_headers(owner, org))
    assert versions.status_code == 200
    assert len(versions.json()) >= 1


def test_due_listing_and_disabled_future_rules(client):
    owner = _register(client, "p26-owner2@example.com", "Pass1234!@", "P26 Org2")
    org = _org_id(client, owner)

    due_rule = _create_rule(client, owner, org)
    future_rule = _create_rule(client, owner, org)
    disabled_rule = _create_rule(client, owner, org)

    client.patch(
        f"/api/v1/automation/rules/{due_rule}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "hourly",
            "schedule_start_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        },
    )
    client.patch(
        f"/api/v1/automation/rules/{future_rule}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "daily",
            "schedule_start_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    client.patch(
        f"/api/v1/automation/rules/{disabled_rule}/schedule",
        headers=_headers(owner, org),
        json={"schedule_enabled": False},
    )

    due = client.get("/api/v1/automation/schedules/due", headers=_headers(owner, org))
    assert due.status_code == 200
    ids = {item["id"] for item in due.json()}
    assert due_rule in ids
    assert future_rule not in ids
    assert disabled_rule not in ids


def test_dry_run_would_create_and_does_not_block_live(client, db_session):
    owner = _register(client, "p26-owner3@example.com", "Pass1234!@", "P26 Org3")
    org = _org_id(client, owner)

    _create_risk_without_owner(client, owner, org)
    rule_id = _create_rule(client, owner, org, trigger_type="manual_scan")

    dry = client.post(f"/api/v1/automation/rules/{rule_id}/dry-run", headers=_headers(owner, org))
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True

    task_count_after_dry = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).count()
    assert task_count_after_dry == 0
    outbox_count_after_dry = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org)).count()
    assert outbox_count_after_dry == 0

    execs = client.get("/api/v1/automation/executions", headers=_headers(owner, org)).json()
    detail = client.get(f"/api/v1/automation/executions/{execs[0]['id']}", headers=_headers(owner, org)).json()
    assert any(item["action_status"] == "would_create" for item in detail["action_logs"])

    live = client.post(f"/api/v1/automation/rules/{rule_id}/run", headers=_headers(owner, org))
    assert live.status_code == 200
    assert live.json()["action_count"] >= 1

    task_count_after_live = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).count()
    assert task_count_after_live >= 1


def test_run_due_scheduled_live_updates_next_run_and_summary(client):
    owner = _register(client, "p26-owner4@example.com", "Pass1234!@", "P26 Org4")
    org = _org_id(client, owner)

    _create_risk_without_owner(client, owner, org, "sched risk")
    rule_id = _create_rule(client, owner, org)
    scheduled = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "hourly",
            "schedule_start_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    before_next = scheduled.json()["next_run_at"]

    run_due = client.post(
        "/api/v1/automation/schedules/run-due",
        headers=_headers(owner, org),
        json={"dry_run": False, "limit": 25},
    )
    assert run_due.status_code == 200
    assert run_due.json()["execution_count"] >= 1

    rule_after = client.get(f"/api/v1/automation/rules/{rule_id}", headers=_headers(owner, org)).json()
    assert rule_after["last_scheduled_run_at"] is not None
    assert rule_after["next_run_at"] is not None
    assert rule_after["next_run_at"] != before_next

    summary = client.get("/api/v1/automation/schedules/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    body = summary.json()
    assert body["scheduled_rules"] >= 1
    assert body["enabled_schedules"] >= 1
    assert body["live_scheduled_executions_last_24h"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org)).json()
    actions = [item["action"] for item in logs]
    assert "automation_rule.schedule_updated" in actions
    assert "automation.scheduled_due_run" in actions
