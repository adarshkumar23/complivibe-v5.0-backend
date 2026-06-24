import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/monitoring"


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
        json={
            "title": title,
            "control_type": "policy",
            "criticality": "medium",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_definition(
    client,
    headers: dict[str, str],
    *,
    control_id: str,
    owner_user_id: str,
    name: str = "Monitor definition",
    monitoring_type: str = "manual_check",
    check_frequency: str = "weekly",
) -> dict:
    response = client.post(
        f"{BASE}/definitions",
        headers=headers,
        json={
            "control_id": control_id,
            "name": name,
            "monitoring_type": monitoring_type,
            "check_frequency": check_frequency,
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_phase96_definition_crud_and_lifecycle(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p96-crud")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p96-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="P96 Control")

    definition = _create_definition(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
        name="Weekly Policy Check",
    )
    assert definition["status"] == "active"

    listed = client.get(f"{BASE}/definitions", headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"{BASE}/definitions/{definition['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == definition["id"]

    updated = client.patch(
        f"{BASE}/definitions/{definition['id']}",
        headers=org["org_headers"],
        json={"name": "Updated Weekly Check", "notes": "monitor notes"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Weekly Check"

    deactivated = client.post(f"{BASE}/definitions/{definition['id']}/deactivate", headers=org["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"

    activated = client.post(f"{BASE}/definitions/{definition['id']}/activate", headers=org["org_headers"])
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    archived = client.post(
        f"{BASE}/definitions/{definition['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "retired check"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_phase96_owner_validation_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p96-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="p96-tenant-b")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "p96-owner1@example.com", "admin")
    owner2 = _create_active_user_with_role(db_session, org2["organization_id"], "p96-owner2@example.com", "admin")
    control1 = _create_control(client, org1["org_headers"], title="P96 Org1 Control")

    bad_owner = client.post(
        f"{BASE}/definitions",
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "name": "Cross-owner",
            "monitoring_type": "manual_check",
            "check_frequency": "weekly",
            "owner_user_id": str(owner2.id),
        },
    )
    assert bad_owner.status_code == 400
    assert "owner_user_id" in bad_owner.json()["detail"]

    definition = _create_definition(
        client,
        org1["org_headers"],
        control_id=control1["id"],
        owner_user_id=str(owner1.id),
        name="Scoped definition",
    )

    cross_get = client.get(f"{BASE}/definitions/{definition['id']}", headers=org2["org_headers"])
    assert cross_get.status_code == 404

    _ = owner2


def test_phase96_result_recording_and_next_due_computation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p96-result")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p96-result-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="Result Control")

    definition = _create_definition(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
        name="Daily Monitor",
        check_frequency="daily",
    )

    recorded = client.post(
        f"{BASE}/definitions/{definition['id']}/record-result",
        headers=org["org_headers"],
        json={"check_status": "pass", "result_summary": "all good", "result_detail_json": {"evidence": 3}},
    )
    assert recorded.status_code == 201
    body = recorded.json()
    assert body["check_status"] == "pass"

    checked_at = datetime.fromisoformat(body["checked_at"].replace("Z", "+00:00"))
    next_due = datetime.fromisoformat(body["next_check_due_at"].replace("Z", "+00:00"))
    assert timedelta(hours=23, minutes=59) <= (next_due - checked_at) <= timedelta(days=1, minutes=1)

    definition_detail = client.get(f"{BASE}/definitions/{definition['id']}", headers=org["org_headers"])
    assert definition_detail.status_code == 200
    assert definition_detail.json()["last_checked_at"] is not None
    assert definition_detail.json()["next_check_due_at"] is not None

    results = client.get(f"{BASE}/definitions/{definition['id']}/results", headers=org["org_headers"])
    assert results.status_code == 200
    assert len(results.json()) == 1

    org_results = client.get(f"{BASE}/results", headers=org["org_headers"])
    assert org_results.status_code == 200
    assert len(org_results.json()) == 1


def test_phase96_archived_definition_blocks_new_results(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p96-arch")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p96-arch-owner@example.com", "admin")
    control = _create_control(client, org["org_headers"], title="Archive Control")

    definition = _create_definition(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
        name="Archive monitor",
    )

    archived = client.post(
        f"{BASE}/definitions/{definition['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200

    blocked = client.post(
        f"{BASE}/definitions/{definition['id']}/record-result",
        headers=org["org_headers"],
        json={"check_status": "fail", "result_summary": "should block"},
    )
    assert blocked.status_code == 400


def test_phase96_summary_metrics_and_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p96-summary")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p96-summary-owner@example.com", "admin")
    control_a = _create_control(client, org["org_headers"], title="Summary Control A")
    control_b = _create_control(client, org["org_headers"], title="Summary Control B")
    control_c = _create_control(client, org["org_headers"], title="Summary Control C")

    active_def = _create_definition(
        client,
        org["org_headers"],
        control_id=control_a["id"],
        owner_user_id=str(owner.id),
        name="Active monitor",
        monitoring_type="manual_check",
        check_frequency="weekly",
    )
    inactive_def = _create_definition(
        client,
        org["org_headers"],
        control_id=control_b["id"],
        owner_user_id=str(owner.id),
        name="Inactive monitor",
        monitoring_type="test_frequency",
        check_frequency="monthly",
    )
    archived_def = _create_definition(
        client,
        org["org_headers"],
        control_id=control_c["id"],
        owner_user_id=str(owner.id),
        name="Archived monitor",
        monitoring_type="evidence_freshness",
        check_frequency="quarterly",
    )

    deactivated = client.post(f"{BASE}/definitions/{inactive_def['id']}/deactivate", headers=org["org_headers"])
    assert deactivated.status_code == 200
    archived = client.post(
        f"{BASE}/definitions/{archived_def['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "archive for summary"},
    )
    assert archived.status_code == 200

    recorded = client.post(
        f"{BASE}/definitions/{active_def['id']}/record-result",
        headers=org["org_headers"],
        json={"check_status": "warning", "result_summary": "drift warning"},
    )
    assert recorded.status_code == 201

    updated = client.patch(
        f"{BASE}/definitions/{active_def['id']}",
        headers=org["org_headers"],
        json={"notes": "updated for audit"},
    )
    assert updated.status_code == 200

    summary_default = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary_default.status_code == 200
    body = summary_default.json()
    assert body["total_definitions"] == 3
    assert body["active_definitions"] == 1
    assert body["inactive_definitions"] == 1
    assert body["archived_definitions"] == 1
    assert body["total_results"] == 1
    assert body["by_monitoring_type"] == {"manual_check": 1}
    assert body["by_check_status"] == {"warning": 1}

    summary_all = client.get(f"{BASE}/summary?include_inactive=true&include_archived=true", headers=org["org_headers"])
    assert summary_all.status_code == 200
    assert summary_all.json()["total_definitions"] == 3

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "control_monitoring_definition.created" in actions
    assert "control_monitoring_definition.updated" in actions
    assert "control_monitoring_definition.archived" in actions
    assert "control_monitoring_result.recorded" in actions
