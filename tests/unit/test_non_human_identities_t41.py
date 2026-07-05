from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select

from app.api.v1.non_human_identities import router as non_human_identity_router
from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.non_human_identity import NonHumanIdentity
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/non-human-identities"


def _ensure_router(app) -> None:
    if not any(getattr(route, "path", "") == BASE for route in app.routes):
        app.include_router(non_human_identity_router, prefix="/api/v1")


def _create_active_user_with_role(db_session, org_id: str, *, email: str, role_name: str = "admin") -> User:
    role = db_session.execute(
        select(Role).where(Role.organization_id == uuid.UUID(org_id), Role.name == role_name)
    ).scalar_one()
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
    db_session.add(Membership(organization_id=uuid.UUID(org_id), user_id=user.id, role_id=role.id, status="active"))
    db_session.commit()
    return user


def _create_identity(client, headers: dict[str, str], *, owner_user_id: str, name: str = "svc-prod") -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "name": name,
            "identity_type": "service_account",
            "owner_user_id": owner_user_id,
            "permissions_scope": "read:controls write:evidence",
            "environment": "prod",
            "last_used_at": (datetime.now(UTC) - timedelta(days=120)).isoformat(),
            "rotation_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_t41_non_human_identity_crud_summary_and_audit(client, db_session, _test_app):
    _ensure_router(_test_app)
    org_a = bootstrap_org_user(client, email_prefix="t41-nhi-a")
    org_b = bootstrap_org_user(client, email_prefix="t41-nhi-b")
    owner = _create_active_user_with_role(db_session, org_a["organization_id"], email="t41-owner@example.com")

    created = _create_identity(client, org_a["org_headers"], owner_user_id=str(owner.id))
    assert created["identity_type"] == "service_account"
    assert created["is_active"] is True
    assert created["status"] == "active"

    listed = client.get(BASE, headers=org_a["org_headers"])
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [created["id"]]

    summary = client.get(f"{BASE}/summary", headers=org_a["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_identities"] == 1
    assert body["stale_identities"] == 1
    assert body["unrotated_identities"] == 1
    assert body["orphaned_identities"] == 0
    assert body["by_type"] == {"service_account": 1}

    updated = client.patch(
        f"{BASE}/{created['id']}",
        headers=org_a["org_headers"],
        json={"identity_type": "api_key", "risk_level": "medium", "last_used_at": datetime.now(UTC).isoformat()},
    )
    assert updated.status_code == 200
    assert updated.json()["identity_type"] == "api_key"
    assert updated.json()["risk_level"] == "medium"

    cross_org = client.get(f"{BASE}/{created['id']}", headers=org_b["org_headers"])
    assert cross_org.status_code == 404

    deleted = client.delete(f"{BASE}/{created['id']}", headers=org_a["org_headers"])
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert deleted.json()["is_active"] is False
    assert deleted.json()["deleted_at"] is not None

    hidden_after_delete = client.get(BASE, headers=org_a["org_headers"])
    assert hidden_after_delete.status_code == 200
    assert hidden_after_delete.json() == []

    actions = set(
        db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == uuid.UUID(org_a["organization_id"]),
                AuditLog.entity_id == uuid.UUID(created["id"]),
            )
        ).scalars().all()
    )
    assert {"non_human_identity.created", "non_human_identity.updated", "non_human_identity.deleted"}.issubset(actions)


def test_t41_flag_orphaned_cross_checks_users_table_without_deleting(client, db_session, _test_app):
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="t41-orphan")
    owner = _create_active_user_with_role(db_session, org["organization_id"], email="t41-orphan-owner@example.com")
    active_owner = _create_active_user_with_role(db_session, org["organization_id"], email="t41-active-owner@example.com")

    orphan_candidate = _create_identity(client, org["org_headers"], owner_user_id=str(owner.id), name="orphan-candidate")
    healthy = _create_identity(client, org["org_headers"], owner_user_id=str(active_owner.id), name="healthy")

    owner.is_active = False
    owner.status = "deactivated"
    db_session.commit()

    scan = client.post(f"{BASE}/flag-orphaned", headers=org["org_headers"])
    assert scan.status_code == 200
    assert scan.json() == {"identities_scanned": 1, "orphaned_flagged": 1, "already_orphaned": 0}

    flagged = client.get(f"{BASE}/{orphan_candidate['id']}", headers=org["org_headers"])
    assert flagged.status_code == 200
    assert flagged.json()["status"] == "orphaned"
    assert flagged.json()["is_active"] is True
    assert flagged.json()["is_orphaned"] is True
    assert flagged.json()["risk_level"] == "high"

    still_healthy = client.get(f"{BASE}/{healthy['id']}", headers=org["org_headers"])
    assert still_healthy.status_code == 200
    assert still_healthy.json()["status"] == "active"
    assert still_healthy.json()["is_orphaned"] is False

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["orphaned_identities"] == 1
    assert summary.json()["high_risk_identities"] == 1

    rows = db_session.execute(
        select(NonHumanIdentity).where(NonHumanIdentity.organization_id == uuid.UUID(org["organization_id"]))
    ).scalars().all()
    assert len(rows) == 2

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(orphan_candidate["id"]),
            AuditLog.action == "non_human_identity.orphaned_flagged",
        )
    ).scalar_one()
    assert audit.metadata_json["source"] == "orphan_scan"

    second_scan = client.post(f"{BASE}/flag-orphaned", headers=org["org_headers"])
    assert second_scan.status_code == 200
    assert second_scan.json() == {"identities_scanned": 1, "orphaned_flagged": 0, "already_orphaned": 1}
