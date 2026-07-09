"""Repro + regression coverage for G1 item 1: running offboarding reassigned data ownership
but never actually revoked the offboarded user's login/session access.
"""
import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.user import User
from app.models.user_session import UserSession


def _register(client, email, password="Pass1234!@", org_name="Org"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "organization_name": org_name})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(token, org_id=None):
    h = {"Authorization": f"Bearer {token}"}
    if org_id:
        h["X-Organization-ID"] = org_id
    return h


def _org_id(client, token):
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _activate_invited_user(db_session, user_id: str, membership_id: str, password: str = "Pass1234!@") -> None:
    user = db_session.execute(select(User).where(User.id == uuid.UUID(user_id))).scalar_one()
    user.hashed_password = get_password_hash(password)
    user.is_active = True
    user.status = "active"
    membership = db_session.execute(select(Membership).where(Membership.id == uuid.UUID(membership_id))).scalar_one()
    membership.status = "active"
    db_session.commit()


def test_offboarding_run_revokes_login_and_active_sessions(client, db_session):
    admin_token = _register(client, "g1-off-admin@example.com", org_name="G1 Offboarding Org")
    org_id = _org_id(client, admin_token)

    invite = client.post(
        "/api/v1/memberships",
        headers=_headers(admin_token, org_id),
        json={"email": "g1-off-victim@example.com", "role_name": "compliance_manager"},
    )
    assert invite.status_code == 201, invite.text
    membership_id = invite.json()["id"]
    user_id = invite.json()["user"]["id"]
    _activate_invited_user(db_session, user_id, membership_id)

    login_before = client.post("/api/v1/auth/login", json={"email": "g1-off-victim@example.com", "password": "Pass1234!@"})
    assert login_before.status_code == 200, login_before.text
    session_token = login_before.json()["access_token"]

    # The victim's own token must work against a protected endpoint before offboarding.
    me_before = client.get("/api/v1/auth/me", headers=_headers(session_token))
    assert me_before.status_code == 200

    run = client.post(
        "/api/v1/compliance/offboarding/run",
        headers=_headers(admin_token, org_id),
        json={"deactivated_user_id": user_id},
    )
    assert run.status_code == 200, run.text

    # 1. The membership itself must be deactivated -- not just left "active" with ownership
    #    quietly reassigned elsewhere.
    membership = db_session.execute(select(Membership).where(Membership.id == uuid.UUID(membership_id))).scalar_one()
    db_session.refresh(membership)
    assert membership.status == "inactive"

    # 2. The user's account must be deactivated too (this was their only org), so a fresh
    #    login attempt is rejected outright.
    user = db_session.execute(select(User).where(User.id == uuid.UUID(user_id))).scalar_one()
    db_session.refresh(user)
    assert user.is_active is False
    assert user.status != "active"

    login_after = client.post("/api/v1/auth/login", json={"email": "g1-off-victim@example.com", "password": "Pass1234!@"})
    assert login_after.status_code == 403, login_after.text

    # 3. Any session the user already held at the time of offboarding must be revoked --
    #    an already-issued token must stop working immediately, not just future logins.
    sessions = db_session.execute(select(UserSession).where(UserSession.user_id == uuid.UUID(user_id))).scalars().all()
    assert sessions, "expected a session row to exist for the pre-offboarding login"
    assert all(s.status == "revoked" for s in sessions)
