import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

ALERTS_BASE = "/api/v1/compliance/monitoring/alerts"
RULES_BASE = "/api/v1/compliance/monitoring/rules"
DEFS_BASE = "/api/v1/compliance/monitoring/definitions"


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
        DEFS_BASE,
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


def _create_rule(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        RULES_BASE,
        headers=headers,
        json={
            "name": name,
            "rule_type": "overdue_check",
            "condition_json": {"days_overdue_threshold": 1},
            "action_type": "create_task",
            "action_config_json": {},
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_manual_alert(
    client,
    headers: dict[str, str],
    *,
    title: str,
    severity: str = "medium",
    rule_id: str | None = None,
    definition_id: str | None = None,
    control_id: str | None = None,
    assigned_to_user_id: str | None = None,
) -> dict:
    payload = {
        "title": title,
        "severity": severity,
        "description": f"desc-{title}",
        "alert_context_json": {"source": "test"},
    }
    if rule_id is not None:
        payload["rule_id"] = rule_id
    if definition_id is not None:
        payload["definition_id"] = definition_id
    if control_id is not None:
        payload["control_id"] = control_id
    if assigned_to_user_id is not None:
        payload["assigned_to_user_id"] = assigned_to_user_id

    response = client.post(ALERTS_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase98_alert_crud_and_filters(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p98-crud")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p98-owner@example.com", "admin")
    assignee = _create_active_user_with_role(db_session, org["organization_id"], "p98-assignee@example.com", "admin")

    control = _create_control(client, org["org_headers"], title="P98 Alert Control")
    definition = _create_definition(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id), name="Alert Def")
    rule = _create_rule(client, org["org_headers"], name="Alert Rule")

    created = _create_manual_alert(
        client,
        org["org_headers"],
        title="Manual Alert",
        severity="high",
        rule_id=rule["id"],
        definition_id=definition["id"],
        control_id=control["id"],
        assigned_to_user_id=str(assignee.id),
    )
    assert created["alert_type"] == "manual"
    assert created["status"] == "open"

    listed = client.get(f"{ALERTS_BASE}", headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    filtered = client.get(
        f"{ALERTS_BASE}?status=open&severity=high&alert_type=manual&assigned_to={assignee.id}&rule_id={rule['id']}&definition_id={definition['id']}&control_id={control['id']}",
        headers=org["org_headers"],
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    detail = client.get(f"{ALERTS_BASE}/{created['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]


def test_phase98_status_transitions_and_terminal_blocking(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p98-lifecycle")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p98-lifecycle-owner@example.com", "admin")

    alert = _create_manual_alert(client, org["org_headers"], title="Lifecycle Alert")

    ack = client.post(f"{ALERTS_BASE}/{alert['id']}/acknowledge", headers=org["org_headers"])
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    assert ack.json()["acknowledged_at"] is not None

    resolved = client.post(
        f"{ALERTS_BASE}/{alert['id']}/resolve",
        headers=org["org_headers"],
        json={"resolution_notes": "resolved now"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None

    dismiss_after_resolve = client.post(
        f"{ALERTS_BASE}/{alert['id']}/dismiss",
        headers=org["org_headers"],
        json={"dismissal_reason": "should fail"},
    )
    assert dismiss_after_resolve.status_code == 400

    assign_after_resolve = client.post(
        f"{ALERTS_BASE}/{alert['id']}/assign",
        headers=org["org_headers"],
        json={"assigned_to_user_id": str(owner.id)},
    )
    assert assign_after_resolve.status_code == 400


def test_phase98_assignee_validation_resolve_requires_notes_dismiss_requires_reason(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p98-validation-a")
    org2 = bootstrap_org_user(client, email_prefix="p98-validation-b")

    assignee_other_org = _create_active_user_with_role(db_session, org2["organization_id"], "p98-cross@example.com", "admin")

    bad_assignee = client.post(
        ALERTS_BASE,
        headers=org1["org_headers"],
        json={
            "title": "Bad assignee alert",
            "severity": "low",
            "assigned_to_user_id": str(assignee_other_org.id),
        },
    )
    assert bad_assignee.status_code == 400

    alert_open = _create_manual_alert(client, org1["org_headers"], title="Resolve Rule Alert")

    resolve_from_open = client.post(
        f"{ALERTS_BASE}/{alert_open['id']}/resolve",
        headers=org1["org_headers"],
        json={"resolution_notes": "not allowed from open"},
    )
    assert resolve_from_open.status_code == 400

    ack = client.post(f"{ALERTS_BASE}/{alert_open['id']}/acknowledge", headers=org1["org_headers"])
    assert ack.status_code == 200

    missing_notes = client.post(f"{ALERTS_BASE}/{alert_open['id']}/resolve", headers=org1["org_headers"], json={})
    assert missing_notes.status_code == 422

    alert_for_dismiss = _create_manual_alert(client, org1["org_headers"], title="Dismiss Rule Alert")
    missing_reason = client.post(f"{ALERTS_BASE}/{alert_for_dismiss['id']}/dismiss", headers=org1["org_headers"], json={})
    assert missing_reason.status_code == 422


def test_phase98_tenant_isolation_and_summary(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p98-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="p98-tenant-b")

    alert_a = _create_manual_alert(client, org1["org_headers"], title="A-high", severity="high")
    alert_b = _create_manual_alert(client, org1["org_headers"], title="A-low", severity="low")
    _ = _create_manual_alert(client, org2["org_headers"], title="B-critical", severity="critical")

    ack = client.post(f"{ALERTS_BASE}/{alert_a['id']}/acknowledge", headers=org1["org_headers"])
    assert ack.status_code == 200
    resolved = client.post(
        f"{ALERTS_BASE}/{alert_a['id']}/resolve",
        headers=org1["org_headers"],
        json={"resolution_notes": "done"},
    )
    assert resolved.status_code == 200

    dismissed = client.post(
        f"{ALERTS_BASE}/{alert_b['id']}/dismiss",
        headers=org1["org_headers"],
        json={"dismissal_reason": "noise"},
    )
    assert dismissed.status_code == 200

    cross_detail = client.get(f"{ALERTS_BASE}/{alert_a['id']}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    summary = client.get(f"{ALERTS_BASE}/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_alerts"] == 2
    assert body["resolved_alerts"] == 1
    assert body["dismissed_alerts"] == 1
    assert body["by_severity"]["high"] == 1
    assert body["by_severity"]["low"] == 1
    assert body["by_status"]["resolved"] == 1
    assert body["by_status"]["dismissed"] == 1


def test_phase98_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p98-audit")
    assignee = _create_active_user_with_role(db_session, org["organization_id"], "p98-audit-assignee@example.com", "admin")

    alert = _create_manual_alert(client, org["org_headers"], title="Audit Alert")

    assigned = client.post(
        f"{ALERTS_BASE}/{alert['id']}/assign",
        headers=org["org_headers"],
        json={"assigned_to_user_id": str(assignee.id)},
    )
    assert assigned.status_code == 200

    acknowledged = client.post(f"{ALERTS_BASE}/{alert['id']}/acknowledge", headers=org["org_headers"])
    assert acknowledged.status_code == 200

    resolved = client.post(
        f"{ALERTS_BASE}/{alert['id']}/resolve",
        headers=org["org_headers"],
        json={"resolution_notes": "resolved for audit"},
    )
    assert resolved.status_code == 200

    second = _create_manual_alert(client, org["org_headers"], title="Audit Dismiss Alert")
    dismissed = client.post(
        f"{ALERTS_BASE}/{second['id']}/dismiss",
        headers=org["org_headers"],
        json={"dismissal_reason": "dismiss for audit"},
    )
    assert dismissed.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "control_monitoring_alert.created" in actions
    assert "control_monitoring_alert.assigned" in actions
    assert "control_monitoring_alert.acknowledged" in actions
    assert "control_monitoring_alert.resolved" in actions
    assert "control_monitoring_alert.dismissed" in actions
