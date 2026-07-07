import contextlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import event, select

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


@contextlib.contextmanager
def _count_select_queries(engine):
    """Count SELECT statements executed against engine within the context."""
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        # SQLite may emit non-SELECT statements mixed in; only count SELECTs.
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


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


def test_phase97_task_overdue_rule_correctly_attributes_matches_across_definitions(client, db_session):
    """Regression test for the task_overdue rule's batched (single grouped-query) match logic:
    with several scoped definitions, only the ones with actually-overdue linked tasks must match
    -- the per-definition attribution must stay correct after batching the lookup."""
    org = bootstrap_org_user(client, email_prefix="p97-task-overdue")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-task-owner@example.com", "admin")

    control_a = _create_control(client, org["org_headers"], title="P97 Task Control A")
    control_b = _create_control(client, org["org_headers"], title="P97 Task Control B")
    control_c = _create_control(client, org["org_headers"], title="P97 Task Control C")

    definition_a = _create_definition(client, org["org_headers"], control_id=control_a["id"], owner_user_id=str(owner.id), name="Task Def A")
    definition_b = _create_definition(client, org["org_headers"], control_id=control_b["id"], owner_user_id=str(owner.id), name="Task Def B")
    definition_c = _create_definition(client, org["org_headers"], control_id=control_c["id"], owner_user_id=str(owner.id), name="Task Def C")

    org_id = uuid.UUID(org["organization_id"])
    now = datetime.now(UTC)

    # A: has an overdue task -> should match.
    db_session.add(
        Task(
            organization_id=org_id,
            title="Overdue linked task",
            status="open",
            priority="normal",
            task_type="general",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            due_date=now - timedelta(days=5),
            linked_entity_type="control_monitoring_definition",
            linked_entity_id=uuid.UUID(definition_a["id"]),
            source="test",
            reminder_status="none",
        )
    )
    # B: has a linked task, but not overdue -> should NOT match.
    db_session.add(
        Task(
            organization_id=org_id,
            title="Future linked task",
            status="open",
            priority="normal",
            task_type="general",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            due_date=now + timedelta(days=5),
            linked_entity_type="control_monitoring_definition",
            linked_entity_id=uuid.UUID(definition_b["id"]),
            source="test",
            reminder_status="none",
        )
    )
    # C: no linked tasks at all -> should NOT match.
    db_session.commit()

    _create_rule(
        client,
        org["org_headers"],
        name="Task Overdue Rule",
        rule_type="task_overdue",
        condition_json={"days_overdue_threshold": 1},
        scope_definition_ids=[definition_a["id"], definition_b["id"], definition_c["id"]],
    )

    evaluated = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": True})
    assert evaluated.status_code == 200
    execution = evaluated.json()["executions"][0]
    assert execution["matched_count"] == 1
    matched_definition_ids = execution["execution_summary_json"]["matched_definition_ids"]
    assert matched_definition_ids == [definition_a["id"]]


def test_phase97_risk_threshold_breach_rule_correctly_attributes_matches_across_controls(client, db_session):
    """Regression test for the risk_threshold_breach rule's batched match logic across multiple
    scoped definitions/controls."""
    from app.models.risk import Risk
    from app.models.risk_control_link import RiskControlLink

    org = bootstrap_org_user(client, email_prefix="p97-risk-breach")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-risk-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    control_high = _create_control(client, org["org_headers"], title="P97 Risk Control High")
    control_low = _create_control(client, org["org_headers"], title="P97 Risk Control Low")

    definition_high = _create_definition(client, org["org_headers"], control_id=control_high["id"], owner_user_id=str(owner.id), name="Risk Def High")
    definition_low = _create_definition(client, org["org_headers"], control_id=control_low["id"], owner_user_id=str(owner.id), name="Risk Def Low")

    high_risk = Risk(
        organization_id=org_id,
        title="High severity risk",
        category="security",
        severity="high",
        likelihood=4,
        impact=5,
        inherent_score=20,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=owner.id,
    )
    low_risk = Risk(
        organization_id=org_id,
        title="Low severity risk",
        category="operational",
        severity="low",
        likelihood=1,
        impact=2,
        inherent_score=2,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=owner.id,
    )
    db_session.add_all([high_risk, low_risk])
    db_session.flush()
    db_session.add_all(
        [
            RiskControlLink(
                organization_id=org_id,
                risk_id=high_risk.id,
                control_id=uuid.UUID(control_high["id"]),
                link_type="mitigates",
                status="active",
            ),
            RiskControlLink(
                organization_id=org_id,
                risk_id=low_risk.id,
                control_id=uuid.UUID(control_low["id"]),
                link_type="mitigates",
                status="active",
            ),
        ]
    )
    db_session.commit()

    _create_rule(
        client,
        org["org_headers"],
        name="Risk Breach Rule",
        rule_type="risk_threshold_breach",
        condition_json={"risk_levels": ["critical", "high"]},
        scope_definition_ids=[definition_high["id"], definition_low["id"]],
    )

    evaluated = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": True})
    assert evaluated.status_code == 200
    execution = evaluated.json()["executions"][0]
    assert execution["matched_count"] == 1
    assert execution["execution_summary_json"]["matched_definition_ids"] == [definition_high["id"]]


def test_phase97_evidence_gap_rule_correctly_attributes_matches_across_controls(client, db_session):
    """Regression test for the evidence_gap rule's batched match logic across multiple scoped
    definitions/controls."""
    org = bootstrap_org_user(client, email_prefix="p97-evidence-gap")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-evidence-owner@example.com", "admin")

    control_with_evidence = _create_control(client, org["org_headers"], title="P97 Evidence Control Fresh")
    control_without_evidence = _create_control(client, org["org_headers"], title="P97 Evidence Control Gap")

    definition_fresh = _create_definition(
        client, org["org_headers"], control_id=control_with_evidence["id"], owner_user_id=str(owner.id), name="Evidence Def Fresh"
    )
    definition_gap = _create_definition(
        client, org["org_headers"], control_id=control_without_evidence["id"], owner_user_id=str(owner.id), name="Evidence Def Gap"
    )

    evidence_resp = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "Fresh Evidence", "evidence_type": "attestation"},
    )
    assert evidence_resp.status_code == 201
    evidence_id = evidence_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=org["org_headers"],
        json={"control_id": control_with_evidence["id"]},
    )
    assert link_resp.status_code == 200

    from app.models.evidence_item import EvidenceItem

    row = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(evidence_id)).one()
    row.collected_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    _create_rule(
        client,
        org["org_headers"],
        name="Evidence Gap Rule",
        rule_type="evidence_gap",
        condition_json={"days_without_evidence": 14},
        scope_definition_ids=[definition_fresh["id"], definition_gap["id"]],
    )

    evaluated = client.post(f"{RULES_BASE}/evaluate", headers=org["org_headers"], json={"dry_run": True})
    assert evaluated.status_code == 200
    execution = evaluated.json()["executions"][0]
    # Only the control with no (or stale) linked evidence should match.
    assert execution["matched_count"] == 1
    assert execution["execution_summary_json"]["matched_definition_ids"] == [definition_gap["id"]]


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


def test_phase97_evidence_gap_rule_batches_queries_for_many_definitions(client, db_session):
    """Adversarial N+1 check: evidence_gap matching must use a single grouped query for all
    scoped definitions, not one query per definition."""
    from app.models.control_monitoring_rule import ControlMonitoringRule
    from app.services.control_monitoring_rule_service import ControlMonitoringRuleService

    org = bootstrap_org_user(client, email_prefix="p97-n1-ev")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-n1-ev-owner@example.com", "admin")

    definitions: list[dict] = []
    for i in range(5):
        control = _create_control(client, org["org_headers"], title=f"P97 Evidence Control {i}")
        definition = _create_definition(
            client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name=f"Evidence Def {i}"
        )
        definitions.append(definition)

    rule = _create_rule(
        client,
        org["org_headers"],
        name="Evidence Gap Batch Rule",
        rule_type="evidence_gap",
        condition_json={"days_without_evidence": 14},
        action_type="create_alert",
        scope_definition_ids=[d["id"] for d in definitions],
    )

    row = db_session.execute(select(ControlMonitoringRule).where(ControlMonitoringRule.id == uuid.UUID(rule["id"]))).scalar_one()
    service = ControlMonitoringRuleService(db_session)

    with _count_select_queries(db_session.get_bind()) as selects:
        matches = service._definition_matches(uuid.UUID(org["organization_id"]), row)

    assert len(matches) == 5
    matched_ids = {str(m["definition"].id) for m in matches}
    assert matched_ids == {d["id"] for d in definitions}
    # With the N+1 fix we expect one query for definitions and one grouped evidence query.
    # Allow a small cushion for any incidental selects.
    select_count = len(selects)
    assert select_count <= 3, f"expected batched evidence_gap queries, got {select_count} SELECTs"


def test_phase97_task_overdue_rule_batches_queries_for_many_definitions(client, db_session):
    """Adversarial N+1 check: task_overdue matching must use a single grouped query for all
    scoped definitions, not one query per definition."""
    from app.models.control_monitoring_rule import ControlMonitoringRule
    from app.services.control_monitoring_rule_service import ControlMonitoringRuleService

    org = bootstrap_org_user(client, email_prefix="p97-n1-task")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-n1-task-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])
    now = datetime.now(UTC)

    definitions: list[dict] = []
    for i in range(5):
        control = _create_control(client, org["org_headers"], title=f"P97 Task Control {i}")
        definition = _create_definition(
            client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name=f"Task Def {i}"
        )
        definitions.append(definition)
        # Every definition gets an overdue task so they all match.
        db_session.add(
            Task(
                organization_id=org_id,
                title=f"Overdue task {i}",
                status="open",
                priority="normal",
                task_type="general",
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
                due_date=now - timedelta(days=5),
                linked_entity_type="control_monitoring_definition",
                linked_entity_id=uuid.UUID(definition["id"]),
                source="test",
                reminder_status="none",
            )
        )
    db_session.commit()

    rule = _create_rule(
        client,
        org["org_headers"],
        name="Task Overdue Batch Rule",
        rule_type="task_overdue",
        condition_json={"days_overdue_threshold": 1},
        action_type="create_alert",
        scope_definition_ids=[d["id"] for d in definitions],
    )

    row = db_session.execute(select(ControlMonitoringRule).where(ControlMonitoringRule.id == uuid.UUID(rule["id"]))).scalar_one()
    service = ControlMonitoringRuleService(db_session)

    with _count_select_queries(db_session.get_bind()) as selects:
        matches = service._definition_matches(uuid.UUID(org["organization_id"]), row)

    assert len(matches) == 5
    select_count = len(selects)
    assert select_count <= 3, f"expected batched task_overdue queries, got {select_count} SELECTs"


def test_phase97_risk_threshold_breach_rule_batches_queries_for_many_definitions(client, db_session):
    """Adversarial N+1 check: risk_threshold_breach matching must use a single grouped query
    for all scoped definitions, not one query per definition."""
    from app.models.control_monitoring_rule import ControlMonitoringRule
    from app.models.risk import Risk
    from app.models.risk_control_link import RiskControlLink
    from app.services.control_monitoring_rule_service import ControlMonitoringRuleService

    org = bootstrap_org_user(client, email_prefix="p97-n1-risk")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p97-n1-risk-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    definitions: list[dict] = []
    risks: list[Risk] = []
    for i in range(5):
        control = _create_control(client, org["org_headers"], title=f"P97 Risk Control {i}")
        definition = _create_definition(
            client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name=f"Risk Def {i}"
        )
        definitions.append(definition)
        risk = Risk(
            organization_id=org_id,
            title=f"High severity risk {i}",
            category="security",
            severity="high",
            likelihood=4,
            impact=5,
            inherent_score=20,
            treatment_strategy="mitigate",
            status="identified",
            owner_user_id=owner.id,
        )
        db_session.add(risk)
        risks.append(risk)
    db_session.flush()

    for definition, risk in zip(definitions, risks):
        db_session.add(
            RiskControlLink(
                organization_id=org_id,
                risk_id=risk.id,
                control_id=uuid.UUID(definition["control_id"]),
                link_type="mitigates",
                status="active",
            )
        )
    db_session.commit()

    rule = _create_rule(
        client,
        org["org_headers"],
        name="Risk Breach Batch Rule",
        rule_type="risk_threshold_breach",
        condition_json={"risk_levels": ["critical", "high"]},
        action_type="create_alert",
        scope_definition_ids=[d["id"] for d in definitions],
    )

    row = db_session.execute(select(ControlMonitoringRule).where(ControlMonitoringRule.id == uuid.UUID(rule["id"]))).scalar_one()
    service = ControlMonitoringRuleService(db_session)

    with _count_select_queries(db_session.get_bind()) as selects:
        matches = service._definition_matches(uuid.UUID(org["organization_id"]), row)

    assert len(matches) == 5
    select_count = len(selects)
    assert select_count <= 3, f"expected batched risk_threshold_breach queries, got {select_count} SELECTs"
