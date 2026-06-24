import uuid
from datetime import UTC, datetime, timedelta

from app.models.control_test_run import ControlTestRun
from app.models.membership import Membership
from app.models.role import Role
from app.models.score_snapshot import ScoreSnapshot
from app.models.user import User
from app.core.security import get_password_hash


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


def _create_control(client, token: str, org_id: str, title: str = "Control27") -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_evidence(client, token: str, org_id: str, title: str = "Evidence27") -> str:
    resp = client.post(
        "/api/v1/evidence",
        headers=_headers(token, org_id),
        json={"title": title, "evidence_type": "attestation", "valid_until": (datetime.now(UTC) + timedelta(days=30)).isoformat()},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_control_test_definition_create_update_archive_and_tenant_scope(client, db_session):
    owner1 = _register(client, "p27-owner1@example.com", "Pass1234!@", "P27 Org1")
    owner2 = _register(client, "p27-owner2@example.com", "Pass1234!@", "P27 Org2")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    other_org_member = _create_active_user_with_role(db_session, org2, "p27-other-owner@example.com", "admin")
    same_org_member = _create_active_user_with_role(db_session, org1, "p27-same-owner@example.com", "admin")

    control_id = _create_control(client, owner1, org1, "Control A")

    invalid_check = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(owner1, org1),
        json={
            "name": "Invalid check",
            "test_type": "internal_metadata_check",
            "check_key": "bad_check",
            "cadence": "monthly",
        },
    )
    assert invalid_check.status_code == 400

    bad_owner = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(owner1, org1),
        json={
            "name": "Owner mismatch",
            "test_type": "manual_attestation",
            "check_key": "manual_attestation",
            "cadence": "weekly",
            "owner_user_id": str(other_org_member.id),
        },
    )
    assert bad_owner.status_code == 400

    created = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(owner1, org1),
        json={
            "name": "Monthly attestation",
            "test_type": "manual_attestation",
            "check_key": "manual_attestation",
            "cadence": "monthly",
            "owner_user_id": str(same_org_member.id),
            "next_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert created.status_code == 201
    test_id = created.json()["id"]

    list_ok = client.get(f"/api/v1/controls/{control_id}/tests", headers=_headers(owner1, org1))
    assert list_ok.status_code == 200
    assert any(row["id"] == test_id for row in list_ok.json())

    cross_tenant = client.get(f"/api/v1/controls/{control_id}/tests", headers=_headers(owner2, org2))
    assert cross_tenant.status_code == 404

    updated = client.patch(
        f"/api/v1/control-tests/{test_id}",
        headers=_headers(owner1, org1),
        json={"name": "Monthly attestation v2", "cadence": "quarterly"},
    )
    assert updated.status_code == 200
    assert updated.json()["cadence"] == "quarterly"

    archived = client.post(f"/api/v1/control-tests/{test_id}/archive", headers=_headers(owner1, org1))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1)).json()
    actions = [item["action"] for item in logs]
    assert "control_test.created" in actions
    assert "control_test.updated" in actions
    assert "control_test.archived" in actions


def test_control_test_run_manual_and_internal_checks_with_dry_run(client, db_session):
    owner = _register(client, "p27-owner3@example.com", "Pass1234!@", "P27 Org3")
    org = _org_id(client, owner)

    control_id = _create_control(client, owner, org, "Control Test Run")

    manual_def = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(owner, org),
        json={
            "name": "Manual check",
            "test_type": "manual_attestation",
            "check_key": "manual_attestation",
            "cadence": "weekly",
            "next_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert manual_def.status_code == 201
    manual_test_id = manual_def.json()["id"]

    missing_manual_result = client.post(
        f"/api/v1/control-tests/{manual_test_id}/run",
        headers=_headers(owner, org),
        json={},
    )
    assert missing_manual_result.status_code == 400

    dry_run = client.post(
        f"/api/v1/control-tests/{manual_test_id}/run",
        headers=_headers(owner, org),
        json={"manual_result": "passed", "dry_run": True},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["dry_run"] is True
    assert dry_run.json()["run"] is None

    run_count_after_dry = db_session.query(ControlTestRun).filter(ControlTestRun.organization_id == uuid.UUID(org)).count()
    assert run_count_after_dry == 0

    real_run = client.post(
        f"/api/v1/control-tests/{manual_test_id}/run",
        headers=_headers(owner, org),
        json={"manual_result": "passed", "result_reason": "completed review"},
    )
    assert real_run.status_code == 200
    assert real_run.json()["dry_run"] is False
    assert real_run.json()["run"]["result"] == "passed"

    internal_def = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(owner, org),
        json={
            "name": "Implemented state check",
            "test_type": "internal_metadata_check",
            "check_key": "control_status_implemented",
            "cadence": "monthly",
        },
    )
    assert internal_def.status_code == 201
    internal_test_id = internal_def.json()["id"]

    failed_check = client.post(
        f"/api/v1/control-tests/{internal_test_id}/run",
        headers=_headers(owner, org),
        json={},
    )
    assert failed_check.status_code == 200
    assert failed_check.json()["run"]["result"] == "failed"

    upd_control = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner, org),
        json={"status": "implemented"},
    )
    assert upd_control.status_code == 200

    passed_check = client.post(
        f"/api/v1/control-tests/{internal_test_id}/run",
        headers=_headers(owner, org),
        json={},
    )
    assert passed_check.status_code == 200
    assert passed_check.json()["run"]["result"] == "passed"

    evidence_id = _create_evidence(client, owner, org, "Verified Evidence")
    link_resp = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=_headers(owner, org),
        json={"control_id": control_id},
    )
    assert link_resp.status_code == 200

    review_resp = client.post(
        f"/api/v1/evidence/{evidence_id}/review",
        headers=_headers(owner, org),
        json={"review_status": "verified", "review_notes": "verified"},
    )
    assert review_resp.status_code == 200

    evidence_def = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(owner, org),
        json={
            "name": "Verified evidence check",
            "test_type": "evidence_review_check",
            "check_key": "has_verified_current_evidence",
            "cadence": "monthly",
        },
    )
    assert evidence_def.status_code == 201

    evidence_run = client.post(
        f"/api/v1/control-tests/{evidence_def.json()['id']}/run",
        headers=_headers(owner, org),
        json={},
    )
    assert evidence_run.status_code == 200
    assert evidence_run.json()["run"]["result"] == "passed"

    runs = client.get(f"/api/v1/controls/{control_id}/test-runs", headers=_headers(owner, org))
    assert runs.status_code == 200
    assert len(runs.json()) >= 4

    summary = client.get("/api/v1/control-tests/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_tests"] >= 3
    assert body["tests_due"] >= 0
    assert body["tests_overdue"] >= 0
    assert body["latest_passed"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org)).json()
    assert "control_test.run_created" in [item["action"] for item in logs]


def test_score_snapshot_materialize_latest_list_and_methodology(client, db_session):
    owner = _register(client, "p27-owner4@example.com", "Pass1234!@", "P27 Org4")
    org = _org_id(client, owner)

    control_id = _create_control(client, owner, org, "Score Control")
    client.patch(f"/api/v1/controls/{control_id}", headers=_headers(owner, org), json={"status": "implemented"})

    dry_run = client.post(
        "/api/v1/scoring/snapshots/materialize",
        headers=_headers(owner, org),
        json={"dry_run": True, "snapshot_types": ["control_health", "evidence_readiness"]},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["dry_run"] is True
    assert len(dry_run.json()["snapshots"]) == 2

    persisted_after_dry = db_session.query(ScoreSnapshot).filter(ScoreSnapshot.organization_id == uuid.UUID(org)).count()
    assert persisted_after_dry == 0

    live_run = client.post(
        "/api/v1/scoring/snapshots/materialize",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert live_run.status_code == 200
    assert live_run.json()["dry_run"] is False
    assert len(live_run.json()["snapshots"]) >= 6

    persisted_after_live = db_session.query(ScoreSnapshot).filter(ScoreSnapshot.organization_id == uuid.UUID(org)).count()
    assert persisted_after_live >= 6

    latest = client.get("/api/v1/scoring/snapshots/latest", headers=_headers(owner, org))
    assert latest.status_code == 200
    latest_rows = latest.json()["snapshots"]
    assert len(latest_rows) >= 6
    assert all(row["inputs_json"] is not None and row["breakdown_json"] is not None for row in latest_rows)

    listed = client.get("/api/v1/scoring/snapshots?snapshot_type=control_health", headers=_headers(owner, org))
    assert listed.status_code == 200
    assert all(row["snapshot_type"] == "control_health" for row in listed.json()["snapshots"])

    methodology = client.get("/api/v1/scoring/methodology", headers=_headers(owner))
    assert methodology.status_code == 200
    body = methodology.json()
    assert "snapshot_types" in body
    assert "control_health" in body["snapshot_types"]
    assert len(body["caveats"]) >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org)).json()
    assert "score_snapshot.materialized" in [item["action"] for item in logs]


def test_score_and_control_test_permissions(client, db_session):
    owner = _register(client, "p27-owner5@example.com", "Pass1234!@", "P27 Org5")
    org = _org_id(client, owner)

    readonly = _create_active_user_with_role(db_session, org, "p27-readonly@example.com", "readonly")
    ro_token = _login(client, readonly.email, "Pass1234!@")

    control_id = _create_control(client, owner, org, "Permission Control")

    ro_create_test = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(ro_token, org),
        json={
            "name": "RO create",
            "test_type": "manual_attestation",
            "check_key": "manual_attestation",
        },
    )
    assert ro_create_test.status_code == 403

    ro_materialize = client.post(
        "/api/v1/scoring/snapshots/materialize",
        headers=_headers(ro_token, org),
        json={"dry_run": True},
    )
    assert ro_materialize.status_code == 200
