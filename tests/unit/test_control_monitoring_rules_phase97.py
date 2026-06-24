import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.role import Role
from app.models.task import Task
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

MONITORING_BASE = "/api/v1/compliance/monitoring"
RULES_BASE = "/api/v1/compliance/monitoring/rules"


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


def _create_definition(client, headers: dict[str, str], *, control_id: str, owner_user_id: str, name: str) -> dict:
    response = client.post(
        f"{MONITORING_BASE}/definitions",
        headers=headers,
        json={
            "control_id": control_id,
            "name": name,
            "monitoring_type": "manual_check",
            "check_frequency": "weekly",
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_rule(
    client,
    headers: dict[str, str],
    *,
    name: str,
    rule_type: str,
    condition_json: dict,
    action_type: str = "create_task",
    action_config_json: dict | None = None,
    scope_definition_ids: list[str] | None = None,
) -> dict:
    payload = {
        "name": name,
        "rule_type": rule_type,
        "condition_json": condition_json,
        "action_type": action_type,
        "action_config_json": action_config_json or {},
    }
    if scope_definition_ids is not None:
        payload["scope_definition_ids"] = scope_definition_ids

    response = client.post(RULES_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _set_definition_due_past(db_session, definition_id: str, days: int = 3) -> None:
    row = db_session.query(ControlMonitoringDefinition).filter(ControlMonitoringDefinition.id == uuid.UUID(definition_id)).one()
    row.next_check_due_at = datetime.now(UTC) - timedelta(days=days)
    db_session.commit()


def test_phase97_rule_crud_and_condition_validation_per_type(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p97-crud")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="P97 CRUD Control")
    definition = _create_definition(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name="P97 Def")

    rule_overdue = _create_rule(
        client,
        org["org_headers"],
        name="Overdue Rule",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 1},
        scope_definition_ids=[definition["id"]],
    )
    assert rule_overdue["status"] == "active"
    assert rule_overdue["rule_type"] == "overdue_check"

    _create_rule(
        client,
        org["org_headers"],
        name="Consecutive Rule",
        rule_type="consecutive_fails",
        condition_json={"fail_count": 2},
    )
    _create_rule(
        client,
        org["org_headers"],
        name="Evidence Rule",
        rule_type="evidence_gap",
        condition_json={"days_without_evidence": 14},
    )
    _create_rule(
        client,
        org["org_headers"],
        name="Task Rule",
        rule_type="task_overdue",
        condition_json={"days_overdue_threshold": 2},
    )
    _create_rule(
        client,
        org["org_headers"],
        name="Risk Rule",
        rule_type="risk_threshold_breach",
        condition_json={"risk_levels": ["critical", "high"]},
    )

    invalid_unknown = client.post(
        RULES_BASE,
        headers=org["org_headers"],
        json={
            "name": "Bad Condition",
            "rule_type": "overdue_check",
            "condition_json": {"days_overdue_threshold": 2, "foo": "bar"},
            "action_type": "create_task",
            "action_config_json": {},
        },
    )
    assert invalid_unknown.status_code == 400

    invalid_fail_count = client.post(
        RULES_BASE,
        headers=org["org_headers"],
        json={
            "name": "Bad Fail",
            "rule_type": "consecutive_fails",
            "condition_json": {"fail_count": 1},
            "action_type": "create_task",
            "action_config_json": {},
        },
    )
    assert invalid_fail_count.status_code == 400

    listed = client.get(RULES_BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 5

    updated = client.patch(
        f"{RULES_BASE}/{rule_overdue['id']}",
        headers=org["org_headers"],
        json={"name": "Overdue Rule Updated", "action_config_json": {"title": "Monitor alert task"}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Overdue Rule Updated"


def test_phase97_dry_run_preview_behavior_and_no_actions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p97-dry")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-dry-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="P97 Dry Control")
    definition = _create_definition(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name="Dry Def")
    _set_definition_due_past(db_session, definition["id"], days=5)

    _create_rule(
        client,
        org["org_headers"],
        name="Dry Overdue",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 2},
        action_type="create_task",
        scope_definition_ids=[definition["id"]],
    )

    task_count_before = db_session.query(Task).count()
    outbox_count_before = db_session.query(EmailOutbox).count()

    evaluated = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": True})
    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["dry_run"] is True
    assert body["evaluated_rules"] == 1
    assert body["executions"][0]["matched_count"] == 1
    assert body["executions"][0]["action_count"] == 1

    assert db_session.query(Task).count() == task_count_before
    assert db_session.query(EmailOutbox).count() == outbox_count_before


def test_phase97_live_evaluation_action_creation_and_idempotency(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p97-live")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-live-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="P97 Live Control")
    definition = _create_definition(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name="Live Def")
    _set_definition_due_past(db_session, definition["id"], days=4)

    _create_rule(
        client,
        org["org_headers"],
        name="Live Reminder",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 1},
        action_type="queue_reminder",
        action_config_json={"task_title": "Reminder task title"},
        scope_definition_ids=[definition["id"]],
    )

    outbox_before = db_session.query(EmailOutbox).count()

    first = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": False})
    assert first.status_code == 200
    first_exec = first.json()["executions"][0]
    assert first_exec["matched_count"] == 1
    assert first_exec["action_count"] == 1
    assert first_exec["skipped_count"] == 0

    assert db_session.query(EmailOutbox).count() == outbox_before + 1

    second = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": False})
    assert second.status_code == 200
    second_exec = second.json()["executions"][0]
    assert second_exec["matched_count"] == 1
    assert second_exec["action_count"] == 0
    assert second_exec["skipped_count"] >= 1


def test_phase97_archived_inactive_skip_and_scope_filtering(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p97-skip")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-skip-owner@example.com", "admin")
    control_a = _create_control(client, org["org_headers"], title="P97 Scope A")
    control_b = _create_control(client, org["org_headers"], title="P97 Scope B")

    definition_a = _create_definition(client, org["org_headers"], control_id=control_a["id"], owner_user_id=str(owner.id), name="Scope A")
    definition_b = _create_definition(client, org["org_headers"], control_id=control_b["id"], owner_user_id=str(owner.id), name="Scope B")
    _set_definition_due_past(db_session, definition_a["id"], days=7)
    _set_definition_due_past(db_session, definition_b["id"], days=7)

    scoped_rule = _create_rule(
        client,
        org["org_headers"],
        name="Scoped rule",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 2},
        scope_definition_ids=[definition_a["id"]],
    )
    inactive_rule = _create_rule(
        client,
        org["org_headers"],
        name="Inactive rule",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 2},
    )
    archived_rule = _create_rule(
        client,
        org["org_headers"],
        name="Archived rule",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 2},
    )

    deactivated = client.post(f"{RULES_BASE}/{inactive_rule['id']}/deactivate", headers=org["org_headers"])
    assert deactivated.status_code == 200

    archived = client.post(
        f"{RULES_BASE}/{archived_rule['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200

    evaluated = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": True})
    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["evaluated_rules"] == 1
    assert body["executions"][0]["rule_id"] == scoped_rule["id"]
    assert body["executions"][0]["matched_count"] == 1


def test_phase97_execution_history_summary_and_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p97-summary")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-summary-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="P97 Summary Control")
    definition = _create_definition(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name="Summary Def")
    _set_definition_due_past(db_session, definition["id"], days=3)

    rule = _create_rule(
        client,
        org["org_headers"],
        name="Summary rule",
        rule_type="overdue_check",
        condition_json={"days_overdue_threshold": 1},
        action_type="create_alert",
    )

    evaluate_live = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": False})
    assert evaluate_live.status_code == 200
    exec_id = evaluate_live.json()["executions"][0]["id"]

    executions = client.get(f"{RULES_BASE}/executions", headers=org["org_headers"])
    assert executions.status_code == 200
    assert len(executions.json()) >= 1

    execution_detail = client.get(f"{RULES_BASE}/executions/{exec_id}", headers=org["org_headers"])
    assert execution_detail.status_code == 200
    assert execution_detail.json()["id"] == exec_id

    summary = client.get(f"{RULES_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_rules"] >= 1
    assert body["active_rules"] >= 1
    assert body["total_executions"] >= 1
    assert body["by_rule_type"]["overdue_check"] >= 1
    assert body["by_action_type"]["create_alert"] >= 1

    updated = client.patch(
        f"{RULES_BASE}/{rule['id']}",
        headers=org["org_headers"],
        json={"description": "updated desc"},
    )
    assert updated.status_code == 200

    archived = client.post(
        f"{RULES_BASE}/{rule['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "archive for audit"},
    )
    assert archived.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "control_monitoring_rule.created" in actions
    assert "control_monitoring_rule.updated" in actions
    assert "control_monitoring_rule.archived" in actions
    assert "control_monitoring_rule.evaluated" in actions
