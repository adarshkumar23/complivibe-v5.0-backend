from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select

from app.api.v1.non_human_identities import router as non_human_identity_router
from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.non_human_identity import NonHumanIdentity
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

NHI_BASE = "/api/v1/non-human-identities"


def _ensure_nhi_router(app) -> None:
    if not any(getattr(route, "path", "") == NHI_BASE for route in app.routes):
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
    membership = Membership(organization_id=uuid.UUID(org_id), user_id=user.id, role_id=role.id, status="active")
    db_session.add(membership)
    db_session.commit()
    return user, membership


def _create_identity(client, headers: dict[str, str], *, owner_user_id: str, name: str = "svc-prod") -> dict:
    response = client.post(
        NHI_BASE,
        headers=headers,
        json={
            "name": name,
            "identity_type": "service_account",
            "owner_user_id": owner_user_id,
            "permissions_scope": "read:controls write:evidence",
            "environment": "prod",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_deactivating_membership_flags_owned_orphaned_nhis(client, db_session, _test_app):
    """BUG: the NHI orphan scanner (NonHumanIdentityService.flag_orphaned_identities)
    is logically correct on its own -- it flags a NonHumanIdentity as orphaned once its
    owner's User is no longer active/status=='active' -- but the real offboarding
    endpoint (PATCH /memberships/{id}/deactivate) never invoked it, so an offboarded
    user's orphaned service accounts/API keys were never actually detected through the
    real flow. This confirms deactivate_membership now wires the scan in.
    """
    _ensure_nhi_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="g2-nhi-offboard")
    owner, membership = _create_active_user_with_role(
        db_session, org["organization_id"], email="g2-nhi-owner@example.com"
    )

    identity = _create_identity(client, org["org_headers"], owner_user_id=str(owner.id))
    assert identity["is_orphaned"] is False

    # Simulate the owner having already been deactivated at the User level (the piece
    # a concurrent fix makes deactivate_membership itself perform) so this test isolates
    # exactly what this change is responsible for: wiring the orphan *scan* into the
    # offboarding call path.
    owner.is_active = False
    owner.status = "inactive"
    db_session.add(owner)
    db_session.commit()

    resp = client.patch(f"/api/v1/memberships/{membership.id}/deactivate", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "inactive"
    assert body["non_human_identities_scanned"] >= 1
    assert body["non_human_identities_orphaned_flagged"] >= 1

    db_session.expire_all()
    row = db_session.get(NonHumanIdentity, uuid.UUID(identity["id"]))
    assert row.is_orphaned is True
    assert row.status == "orphaned"
    assert row.orphan_detected_at is not None
    assert row.risk_reason == "Owner user is inactive or deactivated"


def test_deactivating_membership_with_no_orphans_reports_zero(client, db_session, _test_app):
    _ensure_nhi_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="g2-nhi-offboard-clean")
    owner, membership = _create_active_user_with_role(
        db_session, org["organization_id"], email="g2-nhi-clean-owner@example.com"
    )
    # No NHIs owned by this user, and owner is still active at time of call.
    resp = client.patch(f"/api/v1/memberships/{membership.id}/deactivate", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["non_human_identities_scanned"] == 0
    assert body["non_human_identities_orphaned_flagged"] == 0
