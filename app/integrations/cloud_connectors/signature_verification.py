"""Signature/auth verification for inbound cloud/SaaS connector push events.

Only GitHub and our own AWS bridge use a computed HMAC signature (GitHub natively signs;
AWS EventBridge does not sign arbitrary HTTPS targets, so we mint our own HMAC secret for
that bridge). GCP Pub/Sub push authenticates via a Google-signed OIDC bearer JWT, not
HMAC. Azure Event Grid and Okta Event Hooks authenticate ongoing events via a static
shared-secret header equality check (neither signs the payload) and both require a
one-time verification handshake before they start delivering real events — see
routers/ingest_azure.py and routers/ingest_okta.py for the handshake handling.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi import HTTPException, status

from app.core.url_security import UnsafeURLTargetError, assert_public_http_url

GOOGLE_OIDC_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_OIDC_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def verify_hmac_sha256(*, secret: str, raw_body: bytes, provided_signature: str | None) -> None:
    """Exact pattern used by app.services.issue_sync_service._verify_hmac_signature
    (Linear) and app.services.compliance_bot_service.verify_webhook_signature — HMAC-SHA256
    over the raw request body, optional ``sha256=`` prefix, timing-safe compare."""
    if not provided_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = provided_signature.strip().lower()
    if provided.startswith("sha256="):
        provided = provided[len("sha256="):]
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")


def verify_shared_secret(*, secret: str, provided_secret: str | None) -> None:
    """Static shared-secret equality check (Azure Event Grid custom header / Okta Event
    Hooks Authorization header) — neither provider computes an HMAC over the payload, so
    this is a timing-safe equality check on a pre-shared value, not a signature."""
    if not provided_secret or not hmac.compare_digest(provided_secret.encode(), secret.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing webhook secret")


def _fetch_google_jwks() -> dict[str, Any]:
    try:
        assert_public_http_url(GOOGLE_OIDC_JWKS_URI, field_name="jwks_uri")
    except UnsafeURLTargetError as exc:  # pragma: no cover - constant URL, defensive only
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to fetch OIDC JWKS") from exc
    try:
        response = httpx.get(GOOGLE_OIDC_JWKS_URI, timeout=10.0, follow_redirects=False)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to fetch OIDC JWKS") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC JWKS must contain keys")
    return payload


def verify_gcp_oidc_bearer_token(*, authorization_header: str | None, expected_audience: str, expected_service_account_email: str) -> None:
    """Verify a Google-signed OIDC bearer token from a Pub/Sub push subscription, per
    https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions — same
    JWKS-fetch-and-decode pattern as app.auth.services.oidc_service._validate_id_token,
    reused here rather than adding a new JWT/OIDC dependency (authlib already covers it)."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization_header[len("Bearer "):].strip()

    jwks = _fetch_google_jwks()
    jwt = JsonWebToken(["RS256"])
    try:
        claims = jwt.decode(
            token,
            JsonWebKey.import_key_set(jwks),
            claims_options={
                "iss": {"essential": True, "values": list(GOOGLE_OIDC_ISSUERS)},
                "aud": {"essential": True, "values": [expected_audience]},
                "exp": {"essential": True},
            },
        )
        claims.validate(leeway=60)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC bearer token validation failed") from exc

    if not claims.get("email_verified"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC token email not verified")
    if claims.get("email") != expected_service_account_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC token service account mismatch")
