"""Regression: SSO/OIDC login converges on the password-login session contract (2026-07-20).

Before the fix, the SSO/OIDC callbacks minted a token with NO jti and NO csrf, created
no UserSession, set no cookies, and returned the token in the JSON body -- a
non-revocable, XSS-exposed bearer credential. Now the callback establishes the SAME
session as password login: a jti+csrf access token, a UserSession row, and httpOnly
cv_session + readable cv_csrf cookies (SameSite=Lax), delivered via a 303 redirect with
no body token. It is therefore CSRF-checked and revocable exactly like a password login.

Driven through the real OIDC callback (JWKS / token exchange monkeypatched), reusing the
helpers from test_oidc_sso.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.auth.services.oidc_service import OIDCService
from app.core.security import decode_access_token
from app.models.user_session import UserSession
from app.platform.services.session_service import SessionService
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_oidc_sso import _create_oidc_config, _id_token, _initiate, _key

CARBON_MANUAL = "/api/v1/carbon-accounting/readings/manual"


def _drive_oidc_login(client, db_session, monkeypatch, email: str):
    org = bootstrap_org_user(client, email_prefix="sso-conv")
    _, slug = _create_oidc_config(client, db_session, org, monkeypatch, jit_provisioning=True)
    key = _key("kid-conv")
    monkeypatch.setattr(OIDCService, "_fetch_jwks", lambda self, uri: {"keys": [key.as_dict(is_private=False)]})
    state, nonce = _initiate(client, slug)
    monkeypatch.setattr(
        OIDCService,
        "_fetch_token",
        lambda self, config, code, redirect_uri, db=None: {"id_token": _id_token(key, nonce=nonce, email=email)},
    )
    callback = client.get(
        f"/api/v1/auth/oidc/{slug}/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    return org, callback


def test_oidc_login_issues_jti_csrf_session_cookie_and_no_body_token(client, db_session, monkeypatch):
    org, callback = _drive_oidc_login(client, db_session, monkeypatch, "conv-user@example.com")

    # 303 redirect to the SPA, cookies set on the redirect, and NO token in the body.
    assert callback.status_code == 303, callback.text
    assert "/sso/callback" in callback.headers["location"]
    session_cookie = callback.cookies.get("cv_session")
    csrf_cookie = callback.cookies.get("cv_csrf")
    assert session_cookie and csrf_cookie
    assert not callback.content or b"access_token" not in callback.content

    # The token now carries jti + csrf (pre-fix: neither).
    claims = decode_access_token(session_cookie)
    assert claims.get("jti"), "SSO token must carry a jti"
    assert claims.get("csrf") == csrf_cookie, "csrf claim must match the cv_csrf cookie"
    assert claims.get("auth_method") == "oidc"

    # A real, active UserSession row exists for the jti (pre-fix: none -> non-revocable).
    row = db_session.execute(
        select(UserSession).where(UserSession.token_id == claims["jti"])
    ).scalar_one_or_none()
    assert row is not None
    assert row.status == "active"
    assert str(row.organization_id) == org["organization_id"]


def test_oidc_session_is_csrf_checked_and_revocable_like_password_login(client, db_session, monkeypatch):
    org, callback = _drive_oidc_login(client, db_session, monkeypatch, "conv-csrf@example.com")
    assert callback.status_code == 303, callback.text
    session_cookie = callback.cookies["cv_session"]
    csrf_cookie = callback.cookies["cv_csrf"]
    claims = decode_access_token(session_cookie)

    # Use ONLY the SSO session cookie for subsequent requests.
    client.cookies.clear()
    client.cookies.set("cv_session", session_cookie)
    org_headers = {"X-Organization-ID": org["organization_id"]}
    body = {
        "scope": "scope2",
        "source": "hq",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "value": "1.0",
        "unit": "tCO2e",
    }

    # GET works with the cookie.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "conv-csrf@example.com"

    # A CSRF-protected (mutating) request with the cookie but NO X-CSRF-Token is rejected,
    # exactly as a password-login cookie session would be.
    no_csrf = client.post(CARBON_MANUAL, headers=org_headers, json=body)
    assert no_csrf.status_code == 403
    assert "csrf" in no_csrf.json()["detail"].lower()

    # With the matching X-CSRF-Token the CSRF gate passes (any later 4xx is NOT the CSRF one).
    with_csrf = client.post(CARBON_MANUAL, headers={**org_headers, "X-CSRF-Token": csrf_cookie}, json=body)
    assert "csrf" not in str(with_csrf.json().get("detail", "")).lower()

    # Revoking the session invalidates the token immediately -- the replay-defence that
    # a jti-less, session-less token could never have.
    SessionService(db_session).revoke_session_by_token_id(claims["jti"])
    db_session.commit()
    after = client.get("/api/v1/auth/me")
    assert after.status_code == 401, after.text
