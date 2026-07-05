from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.training_completion_record import TrainingCompletionRecord  # noqa: F401  (registers table on Base.metadata)
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, org_headers

BASE = "/api/v1/training-analytics"
_PERMISSION_CODES = ("training_analytics:read", "training_analytics:write")


@pytest.fixture(scope="session", autouse=True)
def _register_training_analytics_router(_test_app):
    from app.api.v1 import training_analytics as training_analytics_router_module

    already_mounted = any(
        getattr(route, "path", "").startswith("/api/v1/training-analytics") for route in _test_app.routes
    )
    if not already_mounted:
        _test_app.include_router(training_analytics_router_module.router, prefix="/api/v1")
    yield


def _grant_training_analytics_permissions(db_session, organization_id: str) -> None:
    org_uuid = uuid.UUID(organization_id)
    owner_role = db_session.query(Role).filter(
        Role.organization_id == org_uuid, Role.name == "owner"
    ).one()

    for code in _PERMISSION_CODES:
        permission = db_session.query(Permission).filter(Permission.key == code).one_or_none()
        if permission is None:
            permission = Permission(key=code, description=code)
            db_session.add(permission)
            db_session.flush()

        existing_link = db_session.query(RolePermission).filter(
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id == permission.id,
        ).one_or_none()
        if existing_link is None:
            db_session.add(RolePermission(role_id=owner_role.id, permission_id=permission.id))

    db_session.commit()


def _bootstrap(client, db_session, prefix: str) -> dict:
    org = bootstrap_org_user(client, email_prefix=prefix)
    _grant_training_analytics_permissions(db_session, org["organization_id"])
    return org


def _create_read_only_user(db_session, org_id: str, email: str) -> User:
    """A user whose role has training_analytics:read but NOT :write, to test 403 enforcement."""
    role = Role(
        organization_id=uuid.UUID(org_id),
        name=f"ta-readonly-{email.split('@')[0]}",
        description="Training analytics read-only",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.flush()

    read_permission = db_session.execute(
        select(Permission).where(Permission.key == "training_analytics:read")
    ).scalar_one_or_none()
    if read_permission is None:
        read_permission = Permission(key="training_analytics:read", description="training_analytics:read")
        db_session.add(read_permission)
        db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=read_permission.id))

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
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _login_headers(client, user: User, org_id: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Pass1234!@"})
    assert response.status_code == 200
    return org_headers(response.json()["access_token"], org_id)


def _create_bu(db_session, org_id: str, name: str, created_by: str) -> BusinessUnit:
    bu = BusinessUnit(
        organization_id=uuid.UUID(org_id),
        name=name,
        code=name[:10].upper(),
        created_by=uuid.UUID(created_by),
    )
    db_session.add(bu)
    db_session.commit()
    db_session.refresh(bu)
    return bu


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_create_list_and_complete_record_happy_path(client, db_session):
    org = _bootstrap(client, db_session, "ta-happy")
    now = datetime.now(UTC)

    created = client.post(
        BASE + "/records",
        headers=org["org_headers"],
        json={
            "user_id": org["user_id"],
            "training_type": "security_awareness",
            "due_date": _iso(now + timedelta(days=30)),
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["training_type"] == "security_awareness"
    assert body["completed_at"] is None
    assert body["is_overdue"] is False

    listed = client.get(BASE + "/records", headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    completed = client.patch(
        f"{BASE}/records/{body['id']}",
        headers=org["org_headers"],
        json={"score": 88},
    )
    assert completed.status_code == 200
    assert completed.json()["score"] == 88
    assert completed.json()["completed_at"] is not None

    # idempotent re-completion is allowed (documented in service): re-submitting overwrites.
    recompleted = client.patch(
        f"{BASE}/records/{body['id']}",
        headers=org["org_headers"],
        json={"score": 95},
    )
    assert recompleted.status_code == 200
    assert recompleted.json()["score"] == 95


def test_invalid_score_returns_422(client, db_session):
    org = _bootstrap(client, db_session, "ta-badscore")
    now = datetime.now(UTC)
    created = client.post(
        BASE + "/records",
        headers=org["org_headers"],
        json={
            "user_id": org["user_id"],
            "training_type": "phishing_simulation",
            "due_date": _iso(now + timedelta(days=10)),
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]

    bad = client.patch(f"{BASE}/records/{record_id}", headers=org["org_headers"], json={"score": 150})
    assert bad.status_code == 422

    bad_create = client.post(
        BASE + "/records",
        headers=org["org_headers"],
        json={
            "user_id": org["user_id"],
            "training_type": "phishing_simulation",
            "due_date": _iso(now + timedelta(days=10)),
            "score": -1,
        },
    )
    assert bad_create.status_code == 422


def test_cross_org_business_unit_returns_404_no_orphan(client, db_session):
    org1 = _bootstrap(client, db_session, "ta-cross-a")
    org2 = _bootstrap(client, db_session, "ta-cross-b")
    other_org_bu = _create_bu(db_session, org2["organization_id"], "Other Org BU", org2["user_id"])

    response = client.post(
        BASE + "/records",
        headers=org1["org_headers"],
        json={
            "user_id": org1["user_id"],
            "business_unit_id": str(other_org_bu.id),
            "training_type": "code_of_conduct",
            "due_date": _iso(datetime.now(UTC) + timedelta(days=10)),
        },
    )
    assert response.status_code == 404

    orphan_count = (
        db_session.query(TrainingCompletionRecord)
        .filter(TrainingCompletionRecord.organization_id == uuid.UUID(org1["organization_id"]))
        .count()
    )
    assert orphan_count == 0


def test_permission_enforcement_403(client, db_session):
    org = _bootstrap(client, db_session, "ta-perm")
    reader = _create_read_only_user(db_session, org["organization_id"], "ta-reader@example.com")
    reader_headers = _login_headers(client, reader, org["organization_id"])

    blocked_create = client.post(
        BASE + "/records",
        headers=reader_headers,
        json={
            "user_id": org["user_id"],
            "training_type": "data_privacy",
            "due_date": _iso(datetime.now(UTC) + timedelta(days=10)),
        },
    )
    assert blocked_create.status_code == 403

    created = client.post(
        BASE + "/records",
        headers=org["org_headers"],
        json={
            "user_id": org["user_id"],
            "training_type": "data_privacy",
            "due_date": _iso(datetime.now(UTC) + timedelta(days=10)),
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]

    blocked_patch = client.patch(
        f"{BASE}/records/{record_id}",
        headers=reader_headers,
        json={"score": 70},
    )
    assert blocked_patch.status_code == 403

    # reader still has :read, so GET works
    allowed_list = client.get(BASE + "/records", headers=reader_headers)
    assert allowed_list.status_code == 200


def test_audit_log_rows_exist_for_create_and_complete(client, db_session):
    org = _bootstrap(client, db_session, "ta-audit")
    created = client.post(
        BASE + "/records",
        headers=org["org_headers"],
        json={
            "user_id": org["user_id"],
            "training_type": "custom",
            "due_date": _iso(datetime.now(UTC) + timedelta(days=10)),
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]

    completed = client.patch(f"{BASE}/records/{record_id}", headers=org["org_headers"], json={"score": 100})
    assert completed.status_code == 200

    actions = {
        item.action
        for item in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "training_completion_record.created" in actions
    assert "training_completion_record.completed" in actions


def test_summary_computes_per_business_unit_stats_and_flags_trending_bu(client, db_session):
    org = _bootstrap(client, db_session, "ta-summary")
    org_id = org["organization_id"]
    user_id = org["user_id"]
    now = datetime.now(UTC)

    struggling_bu = _create_bu(db_session, org_id, "Struggling BU", user_id)
    healthy_bu = _create_bu(db_session, org_id, "Healthy BU", user_id)

    def _make(business_unit_id, due_delta_days, completed: bool, training_type="security_awareness"):
        due_date = now + timedelta(days=due_delta_days)
        resp = client.post(
            BASE + "/records",
            headers=org["org_headers"],
            json={
                "user_id": user_id,
                "business_unit_id": str(business_unit_id) if business_unit_id else None,
                "training_type": training_type,
                "due_date": _iso(due_date),
            },
        )
        assert resp.status_code == 201
        record_id = resp.json()["id"]
        if completed:
            comp = client.patch(f"{BASE}/records/{record_id}", headers=org["org_headers"], json={"score": 90})
            assert comp.status_code == 200
        return record_id

    # Struggling BU: 4 assigned, 1 completed, 3 overdue (due in the past, not completed)
    _make(struggling_bu.id, -10, completed=False)
    _make(struggling_bu.id, -5, completed=False)
    _make(struggling_bu.id, -3, completed=False)
    _make(struggling_bu.id, -1, completed=True)  # completed despite due date passed -> not overdue

    # Healthy BU: 4 assigned, 3 completed, 0 overdue (all future due dates or completed)
    _make(healthy_bu.id, 30, completed=True)
    _make(healthy_bu.id, 30, completed=True)
    _make(healthy_bu.id, 30, completed=True)
    _make(healthy_bu.id, 30, completed=False)

    # No business unit bucket: 1 overdue
    _make(None, -2, completed=False)

    summary = client.get(BASE + "/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    data = summary.json()

    assert data["total_assigned"] == 9
    assert data["total_completed"] == 4

    by_bu = {bu["business_unit_id"]: bu for bu in data["business_units"]}

    struggling = by_bu[str(struggling_bu.id)]
    assert struggling["total_assigned"] == 4
    assert struggling["completed_count"] == 1
    assert struggling["overdue_count"] == 3
    assert struggling["completion_rate"] == pytest.approx(25.0, abs=0.01)
    assert struggling["trending_toward_noncompliance"] is True
    overdue_types = {d["training_type"] for d in struggling["overdue_details"]}
    assert overdue_types == {"security_awareness"}
    assert len(struggling["overdue_details"]) == 3

    healthy = by_bu[str(healthy_bu.id)]
    assert healthy["total_assigned"] == 4
    assert healthy["completed_count"] == 3
    assert healthy["overdue_count"] == 0
    assert healthy["trending_toward_noncompliance"] is False

    no_bu = by_bu[None]
    assert no_bu["business_unit_name"] == "No business unit assigned"
    assert no_bu["total_assigned"] == 1
    assert no_bu["overdue_count"] == 1

    # Cross-check directly against the DB rows we created.
    db_rows = (
        db_session.query(TrainingCompletionRecord)
        .filter(TrainingCompletionRecord.organization_id == uuid.UUID(org_id))
        .all()
    )
    assert len(db_rows) == 9
    struggling_rows = [r for r in db_rows if r.business_unit_id == struggling_bu.id]
    assert len(struggling_rows) == 4
    struggling_overdue_db = [
        r for r in struggling_rows if r.completed_at is None and r.due_date.replace(tzinfo=None) < now.replace(tzinfo=None)
    ]
    assert len(struggling_overdue_db) == 3
