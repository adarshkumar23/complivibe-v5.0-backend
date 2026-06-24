import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.permission import Permission
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


def _create_risk(client, token: str, org_id: str, title: str, likelihood: int = 5, impact: int = 4):
    return client.post(
        "/api/v1/risks",
        headers=_headers(token, org_id),
        json={"title": title, "category": "operational", "likelihood": likelihood, "impact": impact},
    )


def _create_control(client, token: str, org_id: str, title: str):
    return client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "high"},
    )


def _create_evidence(client, token: str, org_id: str, title: str, freshness_status: str | None = None, review_status: str | None = None):
    created = client.post(
        "/api/v1/evidence",
        headers=_headers(token, org_id),
        json={
            "title": title,
            "evidence_type": "attestation",
            "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat() if freshness_status == "expired" else None,
        },
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]
    if review_status in {"needs_review", "verified", "rejected"}:
        payload = {"review_status": review_status}
        if review_status == "rejected":
            payload["review_notes"] = "no"
        if review_status == "verified":
            payload["review_notes"] = "ok"
        client.post(f"/api/v1/evidence/{evidence_id}/review", headers=_headers(token, org_id), json=payload)
    return evidence_id


def test_automation_permissions_and_rule_crud(client, db_session):
    owner = _register(client, "p25-owner1@example.com", "Pass1234!@", "P25 Org1")
    org = _org_id(client, owner)

    admin = _create_active_user_with_role(db_session, org, "p25-admin@example.com", "admin")
    cm = _create_active_user_with_role(db_session, org, "p25-cm@example.com", "compliance_manager")
    readonly = _create_active_user_with_role(db_session, org, "p25-ro@example.com", "readonly")

    admin_token = _login(client, admin.email, "Pass1234!@")
    cm_token = _login(client, cm.email, "Pass1234!@")
    ro_token = _login(client, readonly.email, "Pass1234!@")

    perms = {p.key for p in db_session.query(Permission).all()}
    assert {"automation:read", "automation:write", "automation:execute"}.issubset(perms)

    invalid_condition = client.post(
        "/api/v1/automation/rules",
        headers=_headers(owner, org),
        json={
            "name": "Bad Cond",
            "trigger_type": "manual_scan",
            "condition_type": "unknown_condition",
            "action_type": "create_task",
        },
    )
    assert invalid_condition.status_code == 400

    invalid_action = client.post(
        "/api/v1/automation/rules",
        headers=_headers(owner, org),
        json={
            "name": "Bad Action",
            "trigger_type": "manual_scan",
            "condition_type": "risk_without_owner",
            "action_type": "unknown_action",
        },
    )
    assert invalid_action.status_code == 400

    for token in [owner, admin_token, cm_token]:
        ok = client.post(
            "/api/v1/automation/rules",
            headers=_headers(token, org),
            json={
                "name": f"Rule {token[:6]}",
                "trigger_type": "manual_scan",
                "condition_type": "risk_without_owner",
                "action_type": "create_task",
            },
        )
        assert ok.status_code == 201

    denied = client.post(
        "/api/v1/automation/rules",
        headers=_headers(ro_token, org),
        json={
            "name": "Readonly deny",
            "trigger_type": "manual_scan",
            "condition_type": "risk_without_owner",
            "action_type": "create_task",
        },
    )
    assert denied.status_code == 403

    listed = client.get("/api/v1/automation/rules", headers=_headers(owner, org))
    assert listed.status_code == 200
    rule_id = listed.json()[0]["id"]

    updated = client.patch(
        f"/api/v1/automation/rules/{rule_id}",
        headers=_headers(owner, org),
        json={"priority": "high", "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    archived = client.post(f"/api/v1/automation/rules/{rule_id}/archive", headers=_headers(owner, org))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_automation_risk_critical_idempotency_and_logs(client, db_session):
    owner = _register(client, "p25-owner2@example.com", "Pass1234!@", "P25 Org2")
    org = _org_id(client, owner)

    risk = _create_risk(client, owner, org, "Critical unmitigated")
    assert risk.status_code == 201
    risk_id = risk.json()["id"]

    rule = client.post(
        "/api/v1/automation/rules",
        headers=_headers(owner, org),
        json={
            "name": "Critical Risk Task",
            "trigger_type": "manual_scan",
            "condition_type": "risk_critical_without_control",
            "action_type": "create_task",
            "priority": "urgent",
        },
    )
    assert rule.status_code == 201
    rule_id = rule.json()["id"]

    run1 = client.post(f"/api/v1/automation/rules/{rule_id}/run", headers=_headers(owner, org))
    assert run1.status_code == 200
    assert run1.json()["matched_count"] >= 1
    assert run1.json()["action_count"] >= 1

    tasks = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org), Task.linked_entity_id == uuid.UUID(risk_id)).all()
    assert len(tasks) == 1

    run2 = client.post(f"/api/v1/automation/rules/{rule_id}/run", headers=_headers(owner, org))
    assert run2.status_code == 200
    tasks_after = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org), Task.linked_entity_id == uuid.UUID(risk_id)).all()
    assert len(tasks_after) == 1

    execs = client.get("/api/v1/automation/executions", headers=_headers(owner, org))
    assert execs.status_code == 200
    exec_id = execs.json()[0]["id"]

    detail = client.get(f"/api/v1/automation/executions/{exec_id}", headers=_headers(owner, org))
    assert detail.status_code == 200
    statuses = [a["action_status"] for a in detail.json()["action_logs"]]
    assert any(s in {"created", "skipped_duplicate"} for s in statuses)


def test_automation_conditions_create_tasks_and_scan_scope(client, db_session):
    owner = _register(client, "p25-owner3@example.com", "Pass1234!@", "P25 Org3")
    other = _register(client, "p25-owner4@example.com", "Pass1234!@", "P25 Org4")
    org = _org_id(client, owner)
    other_org = _org_id(client, other)

    _create_control(client, owner, org, "No Evidence Control")
    _create_evidence(client, owner, org, "Expired Evidence", freshness_status="expired")
    _create_evidence(client, owner, org, "Needs Review Evidence")

    # baseline tasks only in this org
    before_count = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).count()

    # create rules in org1
    for name, cond in [
        ("Control Gap", "control_without_evidence"),
        ("Evidence Expired", "evidence_expired"),
        ("Evidence Needs Review", "evidence_needs_review"),
    ]:
        resp = client.post(
            "/api/v1/automation/rules",
            headers=_headers(owner, org),
            json={
                "name": name,
                "trigger_type": "manual_scan",
                "condition_type": cond,
                "action_type": "create_task",
                "status": "active",
            },
        )
        assert resp.status_code == 201

    # another rule in other org for scope check
    resp_other = client.post(
        "/api/v1/automation/rules",
        headers=_headers(other, other_org),
        json={
            "name": "Other Org Rule",
            "trigger_type": "manual_scan",
            "condition_type": "control_without_evidence",
            "action_type": "create_task",
            "status": "active",
        },
    )
    assert resp_other.status_code == 201

    scan = client.post("/api/v1/automation/run-scan", headers=_headers(owner, org))
    assert scan.status_code == 200
    assert scan.json()["execution_count"] >= 3

    after_count = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).count()
    assert after_count > before_count
    other_count = db_session.query(Task).filter(Task.organization_id == uuid.UUID(other_org)).count()
    assert other_count == 0


def test_automation_task_overdue_email_and_summary(client, db_session):
    owner = _register(client, "p25-owner5@example.com", "Pass1234!@", "P25 Org5")
    org = _org_id(client, owner)
    assignee = _create_active_user_with_role(db_session, org, "p25-assignee@example.com", "admin")

    overdue_with_owner = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org),
        json={
            "title": "Overdue with owner",
            "owner_user_id": str(assignee.id),
            "due_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert overdue_with_owner.status_code == 201

    overdue_no_owner = client.post(
        "/api/v1/tasks",
        headers=_headers(owner, org),
        json={
            "title": "Overdue no owner",
            "due_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert overdue_no_owner.status_code == 201

    rule_active = client.post(
        "/api/v1/automation/rules",
        headers=_headers(owner, org),
        json={
            "name": "Overdue reminders",
            "trigger_type": "manual_scan",
            "condition_type": "task_overdue",
            "action_type": "queue_email_reminder",
            "status": "active",
        },
    )
    assert rule_active.status_code == 201

    rule_inactive = client.post(
        "/api/v1/automation/rules",
        headers=_headers(owner, org),
        json={
            "name": "Inactive",
            "trigger_type": "manual_scan",
            "condition_type": "task_overdue",
            "action_type": "queue_email_reminder",
            "status": "inactive",
        },
    )
    assert rule_inactive.status_code == 201
    rule_inactive_id = rule_inactive.json()["id"]
    archived = client.post(f"/api/v1/automation/rules/{rule_inactive_id}/archive", headers=_headers(owner, org))
    assert archived.status_code == 200

    scan = client.post("/api/v1/automation/run-scan", headers=_headers(owner, org))
    assert scan.status_code == 200
    assert scan.json()["execution_count"] == 1

    outbox = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org)).all()
    assert any(item.status == "pending" and item.sent_at is None for item in outbox)

    executions = client.get("/api/v1/automation/executions", headers=_headers(owner, org)).json()
    assert len(executions) >= 1
    exec_detail = client.get(f"/api/v1/automation/executions/{executions[0]['id']}", headers=_headers(owner, org)).json()
    action_statuses = {item["action_status"] for item in exec_detail["action_logs"]}
    assert "created" in action_statuses or "skipped_invalid" in action_statuses

    summary = client.get("/api/v1/automation/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_rules"] >= 1
    assert body["executions_last_24h"] >= 1
    assert body["actions_created_last_24h"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org)).json()
    actions = [item["action"] for item in logs]
    assert "automation_rule.created" in actions
    assert "automation_rule.executed" in actions or "automation.scan_executed" in actions
