"""Shared login-session issuance for every authentication path.

Both password login and SSO/OIDC callbacks must issue the SAME kind of session: an
access token carrying jti + csrf, a server-side UserSession row (so it is revocable),
and the httpOnly cv_session + readable cv_csrf cookies that get_current_user enforces.
Factoring this here stops the SSO/OIDC paths from diverging into jti-less, session-less,
body-delivered tokens.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from app.core.security import create_access_token, create_csrf_token
from app.platform.services.ip_allowlist_service import IPAllowlistService
from app.platform.services.session_service import SessionService


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    csrf_token: str,
    samesite: str = "strict",
) -> None:
    """Issue the browser-facing session as an httpOnly cookie plus a readable
    double-submit CSRF cookie.

    samesite defaults to "strict" (password login, same-origin). The SSO/OIDC callbacks
    pass "lax" because the browser lands on the callback via a cross-site top-level
    navigation from the identity provider, and a strict cookie would not be sent on
    that navigation.
    """
    settings = get_settings()
    secure = settings.APP_ENV == "production"
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
        max_age=max_age,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite=samesite,
        path="/",
        max_age=max_age,
    )


def establish_login_session(
    response: Response,
    request: Request,
    db: Session,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    extra_claims: dict | None = None,
    samesite: str = "strict",
) -> str:
    """Mint a jti+csrf access token, create the UserSession, and set the auth cookies.

    Returns the raw access token. The caller commits the transaction.
    """
    settings = get_settings()
    csrf_token = create_csrf_token()
    token_id = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    claims: dict = {"jti": token_id, "csrf": csrf_token}
    if extra_claims:
        claims.update(extra_claims)
    access_token = create_access_token(subject=user_id, extra=claims)
    SessionService(db).create_session(
        org_id=org_id,
        user_id=user_id,
        token_id=token_id,
        ip_address=IPAllowlistService.extract_request_ip(
            x_forwarded_for=request.headers.get("X-Forwarded-For"),
            client_host=request.client.host if request.client else None,
            cf_connecting_ip=request.headers.get("CF-Connecting-IP"),
        ),
        user_agent=request.headers.get("user-agent"),
        expires_at=expires_at,
    )
    set_auth_cookies(response, access_token=access_token, csrf_token=csrf_token, samesite=samesite)
    return access_token
