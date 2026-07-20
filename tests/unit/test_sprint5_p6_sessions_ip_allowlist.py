from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models.membership import Membership
from app.models.user_session import UserSession
from app.platform.services.session_service import SessionService
from tests.helpers.auth_org import bootstrap_org_user


def _headers(org_ctx: dict, *, ip: str | None = None, user_agent: str | None = None) -> dict[str, str]:
    headers = dict(org_ctx["org_headers"])
    if ip:
        headers["X-Forwarded-For"] = ip
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def _login(client, *, email: str, password: str = "Pass1234!@", org_id: str | None = None, ip: str | None = None, user_agent: str | None = None) -> str:
    headers: dict[str, str] = {}
    if org_id:
        headers["X-Organization-ID"] = org_id
    if ip:
        headers["X-Forwarded-For"] = ip
    if user_agent:
        headers["User-Agent"] = user_agent
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_s5_p6_sessions_login_list_revoke_admin_cross_org_and_expire(client, db_session, monkeypatch):
    # These tests simulate a client at a given IP via a single X-Forwarded-For entry.
    # After the XFF-spoofing fix, X-Forwarded-For is only trusted when a trusted proxy
    # is declared, so model exactly one trusted proxy and the sole XFF entry (the
    # rightmost, parts[-1]) is taken as the client IP.
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    get_settings.cache_clear()

    org_a = bootstrap_org_user(client, email_prefix="s5p6-sess-a")
    org_b = bootstrap_org_user(client, email_prefix="s5p6-sess-b")

    token = _login(
        client,
        email=org_a["email"],
        org_id=org_a["organization_id"],
        ip="203.0.113.10",
        user_agent="pytest-session-agent",
    )
    claims = decode_access_token(token)
    token_id = claims.get("jti")
    assert isinstance(token_id, str) and token_id

    session_row = db_session.query(UserSession).filter(UserSession.token_id == token_id).first()
    assert session_row is not None
    assert str(session_row.organization_id) == org_a["organization_id"]
    assert str(session_row.user_id) == org_a["user_id"]
    assert session_row.ip_address == "203.0.113.10"
    assert session_row.user_agent == "pytest-session-agent"

    me_sessions = client.get("/api/v1/sessions", headers=org_a["org_headers"])
    assert me_sessions.status_code == 200, me_sessions.text
    assert any(row["token_id"] == token_id for row in me_sessions.json())

    revoke = client.delete(f"/api/v1/sessions/{session_row.id}", headers=org_a["org_headers"])
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"

    denied = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 401, denied.text

    # Create org_b membership inside org_a so we can generate org_a-scoped session for admin view.
    add_member = client.post(
        "/api/v1/memberships",
        headers=org_a["org_headers"],
        json={"email": org_b["email"], "full_name": "Org B in Org A", "role_name": "readonly"},
    )
    assert add_member.status_code == 201, add_member.text

    token_b_in_a = _login(
        client,
        email=org_b["email"],
        org_id=org_a["organization_id"],
    )
    token_b_in_a_id = decode_access_token(token_b_in_a).get("jti")
    assert isinstance(token_b_in_a_id, str) and token_b_in_a_id

    admin_view = client.get(
        f"/api/v1/organizations/users/{org_b['user_id']}/sessions",
        headers=org_a["org_headers"],
    )
    assert admin_view.status_code == 200, admin_view.text
    assert any(row["token_id"] == token_b_in_a_id for row in admin_view.json())

    cross_org = client.get(
        f"/api/v1/organizations/users/{org_a['user_id']}/sessions",
        headers=org_b["org_headers"],
    )
    assert cross_org.status_code == 404, cross_org.text

    stale = SessionService(db_session).create_session(
        org_id=uuid.UUID(org_a["organization_id"]),
        user_id=uuid.UUID(org_a["user_id"]),
        token_id=f"stale-{uuid.uuid4()}",
        ip_address="127.0.0.1",
        user_agent="stale",
        expires_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db_session.flush()
    expired_count = SessionService(db_session).expire_stale_sessions(org_id=uuid.UUID(org_a["organization_id"]))
    assert expired_count >= 1
    assert db_session.get(UserSession, stale.id).status == "expired"


def test_s5_p6_ip_allowlist_add_validate_enforce_deactivate_and_disable(client, db_session, monkeypatch):
    # See the note above: declare one trusted proxy so the single X-Forwarded-For
    # entry is honoured as the client IP under the post-fix extraction rules.
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    get_settings.cache_clear()

    org = bootstrap_org_user(client, email_prefix="s5p6-ip")

    add = client.post(
        "/api/v1/organizations/ip-allowlist",
        headers=_headers(org, ip="203.0.113.2"),
        json={"cidr_range": "203.0.113.0/24", "label": "Office VPN"},
    )
    assert add.status_code == 200, add.text
    range_id = add.json()["id"]

    bad = client.post(
        "/api/v1/organizations/ip-allowlist",
        headers=_headers(org, ip="203.0.113.2"),
        json={"cidr_range": "not-a-cidr", "label": "Bad"},
    )
    assert bad.status_code == 422, bad.text

    allowed = client.get("/api/v1/risks", headers=_headers(org, ip="203.0.113.9"))
    assert allowed.status_code == 200, allowed.text

    blocked = client.get("/api/v1/risks", headers=_headers(org, ip="198.51.100.9"))
    assert blocked.status_code == 403, blocked.text

    # Adding a non-covering range is fine because the requester is still covered
    # by an existing active range.
    non_covering = client.post(
        "/api/v1/organizations/ip-allowlist",
        headers=_headers(org, ip="203.0.113.9"),
        json={"cidr_range": "198.51.100.0/24", "label": "Branch VPN"},
    )
    assert non_covering.status_code == 200, non_covering.text
    non_covering_id = non_covering.json()["id"]

    # Removing the covering range would lock the requester out; must be rejected.
    lockout_attempt = client.delete(
        f"/api/v1/organizations/ip-allowlist/{range_id}",
        headers=_headers(org, ip="203.0.113.9"),
    )
    assert lockout_attempt.status_code == 400, lockout_attempt.text
    assert "locking you out" in lockout_attempt.json()["detail"].lower()

    # Removing a non-covering range is safe and should succeed.
    remove_non_covering = client.delete(
        f"/api/v1/organizations/ip-allowlist/{non_covering_id}",
        headers=_headers(org, ip="203.0.113.9"),
    )
    assert remove_non_covering.status_code == 200, remove_non_covering.text
    assert remove_non_covering.json()["is_active"] is False

    # The requester is still covered by the original range.
    still_allowed = client.get("/api/v1/risks", headers=_headers(org, ip="203.0.113.9"))
    assert still_allowed.status_code == 200, still_allowed.text

    # Explicitly disable IP allowlisting entirely.
    disabled_resp = client.post(
        "/api/v1/organizations/ip-allowlist/disable",
        headers=_headers(org, ip="203.0.113.9"),
    )
    assert disabled_resp.status_code == 200, disabled_resp.text
    deactivated = disabled_resp.json()
    assert any(row["id"] == range_id and row["is_active"] is False for row in deactivated)

    # With no active ranges the organization is no longer IP-restricted.
    now_allowed = client.get("/api/v1/risks", headers=_headers(org, ip="198.51.100.9"))
    assert now_allowed.status_code == 200, now_allowed.text

    # Org with zero active ranges remains unrestricted.
    org2 = bootstrap_org_user(client, email_prefix="s5p6-ip-open")
    unrestricted = client.get("/api/v1/risks", headers=_headers(org2, ip="198.51.100.33"))
    assert unrestricted.status_code == 200, unrestricted.text
