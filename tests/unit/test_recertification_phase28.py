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


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
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


def _create_control(client, token: str, org_id: str, title: str = "Control28") -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_evidence(
    client,
    token: str,
    org_id: str,
    title: str,
    *,
    valid_until: datetime | None = None,
) -> str:
    payload = {"title": title, "evidence_type": "attestation"}
    if valid_until:
        payload["valid_until"] = valid_until.isoformat()
    resp = client.post("/api/v1/evidence", headers=_headers(token, org_id), json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_control_test(
    client,
    token: str,
    org_id: str,
    control_id: str,
    *,
    name: str,
    check_key: str = "control_status_implemented",
    next_due_at: datetime,
) -> str:
    resp = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(token, org_id),
        json={
            "name": name,
            "test_type": "internal_metadata_check",
            "check_key": check_key,
            "cadence": "monthly",
            "next_due_at": next_due_at.isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_recertification_permissions_seeded(client, db_session):
    owner = _register(client, "p28-owner1@example.com", "Pass1234!@", "P28 Org1")
    org = _org_id(client, owner)

    cm_user = _create_active_user_with_role(db_session, org, "p28-cm@example.com", "compliance_manager")
    cm_token = _login(client, cm_user.email, "Pass1234!@")

    perms = client.get("/api/v1/auth/permissions", headers=_headers(cm_token, org))
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "recertification:read" in codes
    assert "recertification:write" in codes
    assert "recertification:execute" in codes


def test_policy_crud_and_validation(client, db_session):
    owner1 = _register(client, "p28-owner2@example.com", "Pass1234!@", "P28 Org2")
    owner2 = _register(client, "p28-owner3@example.com", "Pass1234!@", "P28 Org3")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    other_org_user = _create_active_user_with_role(db_session, org2, "p28-other@example.com", "admin")
    same_org_user = _create_active_user_with_role(db_session, org1, "p28-same@example.com", "admin")

    bad_scope = client.post(
        "/api/v1/recertification/policies",
        headers=_headers(owner1, org1),
        json={"name": "Bad scope", "scope_type": "bad", "cadence": "monthly"},
    )
    assert bad_scope.status_code == 400

    bad_cadence = client.post(
        "/api/v1/recertification/policies",
        headers=_headers(owner1, org1),
        json={"name": "Bad cadence", "scope_type": "all_evidence", "cadence": "weeklyish"},
    )
    assert bad_cadence.status_code == 400

    bad_owner = client.post(
        "/api/v1/recertification/policies",
        headers=_headers(owner1, org1),
        json={
            "name": "Owner mismatch",
            "scope_type": "all_evidence",
            "cadence": "monthly",
            "owner_user_id": str(other_org_user.id),
        },
    )
    assert bad_owner.status_code == 400

    created = client.post(
        "/api/v1/recertification/policies",
        headers=_headers(owner1, org1),
        json={
            "name": "Default policy",
            "scope_type": "all_evidence",
            "cadence": "quarterly",
            "lead_time_days": 10,
            "owner_user_id": str(same_org_user.id),
        },
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]

    listed = client.get("/api/v1/recertification/policies", headers=_headers(owner1, org1))
    assert listed.status_code == 200
    assert any(row["id"] == policy_id for row in listed.json())

    updated = client.patch(
        f"/api/v1/recertification/policies/{policy_id}",
        headers=_headers(owner1, org1),
        json={"lead_time_days": 15, "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["lead_time_days"] == 15
    assert updated.json()["status"] == "inactive"

    archived = client.post(f"/api/v1/recertification/policies/{policy_id}/archive", headers=_headers(owner1, org1))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_due_evidence_discovery_tenant_scoped_and_runs(client, db_session):
    owner1 = _register(client, "p28-owner4@example.com", "Pass1234!@", "P28 Org4")
    owner2 = _register(client, "p28-owner5@example.com", "Pass1234!@", "P28 Org5")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    control_id = _create_control(client, owner1, org1, "Evidence control")

    expired_evidence = _create_evidence(client, owner1, org1, "Expired evidence", valid_until=datetime.now(UTC) - timedelta(days=1))
    expiring_evidence = _create_evidence(client, owner1, org1, "Expiring evidence", valid_until=datetime.now(UTC) + timedelta(days=2))
    needs_review_evidence = _create_evidence(client, owner1, org1, "Needs review evidence")

    _create_evidence(client, owner2, org2, "Other org evidence", valid_until=datetime.now(UTC) - timedelta(days=1))

    link_resp = client.post(
        f"/api/v1/evidence/{expired_evidence}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control_id},
    )
    assert link_resp.status_code == 200

    due = client.get("/api/v1/recertification/evidence/due", headers=_headers(owner1, org1))
    assert due.status_code == 200
    titles = {row["title"] for row in due.json()}
    assert "Expired evidence" in titles
    assert "Expiring evidence" in titles
    assert "Needs review evidence" in titles
    assert "Other org evidence" not in titles

    dry_run = client.post(
        "/api/v1/recertification/evidence/run",
        headers=_headers(owner1, org1),
        json={"dry_run": True, "notify_owner": True, "limit": 20},
    )
    assert dry_run.status_code == 200
    run_id = dry_run.json()["id"]
    assert dry_run.json()["dry_run"] is True

    task_count_after_dry = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org1)).count()
    email_count_after_dry = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org1)).count()
    assert task_count_after_dry == 0
    assert email_count_after_dry == 0

    dry_detail = client.get(f"/api/v1/recertification/runs/{run_id}", headers=_headers(owner1, org1))
    assert dry_detail.status_code == 200
    assert len(dry_detail.json()["action_logs"]) >= 1
    assert all(log["action_status"] == "would_create" for log in dry_detail.json()["action_logs"])

    live_run = client.post(
        "/api/v1/recertification/evidence/run",
        headers=_headers(owner1, org1),
        json={"dry_run": False, "notify_owner": True, "limit": 20},
    )
    assert live_run.status_code == 200
    assert live_run.json()["task_count"] >= 1

    task_count_after_live = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org1)).count()
    email_count_after_live = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org1)).count()
    assert task_count_after_live >= 1
    assert email_count_after_live >= 1
    assert all(item.sent_at is None for item in db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org1)).all())

    second_live = client.post(
        "/api/v1/recertification/evidence/run",
        headers=_headers(owner1, org1),
        json={"dry_run": False, "notify_owner": False, "limit": 20},
    )
    assert second_live.status_code == 200
    assert second_live.json()["skipped_duplicate_count"] >= 1


def test_control_reassessment_runs_summary_and_scoring_trends_delta(client):
    owner = _register(client, "p28-owner6@example.com", "Pass1234!@", "P28 Org6")
    org = _org_id(client, owner)

    control_id = _create_control(client, owner, org, "Reassess control")
    test_id = _create_control_test(
        client,
        owner,
        org,
        control_id,
        name="Monthly reassess",
        next_due_at=datetime.now(UTC) - timedelta(days=1),
    )

    due = client.get("/api/v1/recertification/controls/due", headers=_headers(owner, org))
    assert due.status_code == 200
    assert any(item["test_id"] == test_id for item in due.json())

    dry_run = client.post(
        "/api/v1/recertification/controls/run",
        headers=_headers(owner, org),
        json={"dry_run": True, "notify_owner": False, "due_within_days": 7, "limit": 20},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["dry_run"] is True

    live_run = client.post(
        "/api/v1/recertification/controls/run",
        headers=_headers(owner, org),
        json={"dry_run": False, "notify_owner": False, "due_within_days": 7, "limit": 20},
    )
    assert live_run.status_code == 200
    assert live_run.json()["task_count"] >= 1

    runs = client.get("/api/v1/recertification/runs", headers=_headers(owner, org))
    assert runs.status_code == 200
    assert len(runs.json()) >= 2

    summary = client.get("/api/v1/recertification/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    body = summary.json()
    assert "active_policies" in body
    assert "due_control_tests" in body
    assert "runs_last_24h" in body

    # scoring trends / delta
    first = client.post(
        "/api/v1/scoring/snapshots/materialize",
        headers=_headers(owner, org),
        json={"dry_run": False, "snapshot_types": ["control_health"]},
    )
    assert first.status_code == 200

    client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner, org),
        json={"status": "implemented"},
    )

    second = client.post(
        "/api/v1/scoring/snapshots/materialize",
        headers=_headers(owner, org),
        json={"dry_run": False, "snapshot_types": ["control_health"]},
    )
    assert second.status_code == 200

    trends = client.get("/api/v1/scoring/snapshots/trends?snapshot_type=control_health&days=30", headers=_headers(owner, org))
    assert trends.status_code == 200
    series = trends.json()["series"]
    assert len(series) >= 1
    assert series[0]["snapshot_type"] == "control_health"
    assert len(series[0]["points"]) >= 2

    delta = client.get("/api/v1/scoring/snapshots/delta?snapshot_type=control_health&days=30", headers=_headers(owner, org))
    assert delta.status_code == 200
    delta_body = delta.json()
    assert delta_body["snapshot_type"] == "control_health"
    assert isinstance(delta_body["delta"], int)
    assert delta_body["direction"] in {"improved", "declined", "unchanged"}

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org)).json()
    actions = [item["action"] for item in logs]
    assert "recertification.control_reassessment_run" in actions
