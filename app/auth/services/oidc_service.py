from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.services.oidc_config_service import OIDCConfigService
from app.auth.services.sso_service import SSOService
from app.core.config import get_settings
from app.core.url_security import UnsafeURLTargetError, assert_public_http_url
from app.models.oidc_auth_state import OIDCAuthState
from app.models.oidc_config import OIDCConfig
from app.models.organization import Organization
from app.services.audit_service import AuditService


class OIDCService:
    STATE_TTL_MINUTES = 10
    ALLOWED_ID_TOKEN_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def initiate_login(self, org_slug: str, db: Session) -> str:
        config = self._get_oidc_config(org_slug, db)
        if not config or not config.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC SSO not active for this organization")

        state = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(48)
        redirect_uri = self._callback_url(org_slug)
        db.add(
            OIDCAuthState(
                organization_id=config.organization_id,
                state_hash=self._sha256(state),
                nonce_hash=self._sha256(nonce),
                redirect_uri=redirect_uri,
                expires_at=self.utcnow() + timedelta(minutes=self.STATE_TTL_MINUTES),
            )
        )
        db.flush()

        client = OAuth2Client(
            client_id=config.client_id,
            scope=" ".join(config.scopes or []),
            redirect_uri=redirect_uri,
        )
        authorization_url, _ = client.create_authorization_url(
            config.authorization_endpoint,
            response_type="code",
            scope=" ".join(config.scopes or []),
            state=state,
            nonce=nonce,
        )
        return authorization_url

    def process_callback(self, org_slug: str, code: str, state: str, db: Session) -> dict[str, str]:
        config = self._get_oidc_config(org_slug, db)
        if not config or not config.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC SSO not active for this organization")

        auth_state = self._consume_state(config.organization_id, state, db)
        token = self._fetch_token(config, code, auth_state.redirect_uri, db)
        id_token = token.get("id_token")
        if not id_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC token response missing id_token")

        claims = self._validate_id_token(config, str(id_token), auth_state.nonce_hash)
        email = self._extract_email(claims, config)
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC id_token missing configured email claim")

        user = SSOService()._get_or_create_user(
            email=email,
            org_id=config.organization_id,
            config=config,
            db=db,
        )
        access_token = SSOService()._create_jwt_for_user(user=user, org_id=config.organization_id)

        AuditService(db).write_audit_log(
            action="sso.login",
            entity_type="users",
            organization_id=config.organization_id,
            actor_user_id=user.id,
            entity_id=user.id,
            metadata_json={
                "provider": config.provider,
                "auth_method": "oidc",
                "issuer_url": config.issuer_url,
                "subject": str(claims.get(str((config.claim_mapping or {}).get("subject", "sub"))) or ""),
            },
        )

        return {"access_token": access_token, "token_type": "bearer", "auth_method": "oidc"}

    def _get_oidc_config(self, org_slug: str, db: Session) -> OIDCConfig | None:
        org = db.execute(
            select(Organization).where(
                Organization.slug == org_slug,
                Organization.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if not org:
            return None
        return db.execute(
            select(OIDCConfig).where(
                OIDCConfig.organization_id == org.id,
                OIDCConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def _callback_url(self, org_slug: str) -> str:
        settings = get_settings()
        return f"{settings.BASE_URL.rstrip('/')}/api/v1/auth/oidc/{org_slug}/callback"

    def _consume_state(self, org_id: uuid.UUID, state: str, db: Session) -> OIDCAuthState:
        now = self.utcnow()
        row = db.execute(
            select(OIDCAuthState).where(
                OIDCAuthState.organization_id == org_id,
                OIDCAuthState.state_hash == self._sha256(state),
                OIDCAuthState.consumed_at.is_(None),
                OIDCAuthState.expires_at > now,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OIDC state")
        row.consumed_at = now
        db.flush()
        return row

    def _fetch_token(self, config: OIDCConfig, code: str, redirect_uri: str, db: Session) -> dict[str, Any]:
        client = OAuth2Client(
            client_id=config.client_id,
            client_secret=OIDCConfigService(db).decrypt_secret(
                config.client_secret_enc, organization_id=config.organization_id, entity_id=config.id
            ),
            scope=" ".join(config.scopes or []),
            redirect_uri=redirect_uri,
        )
        try:
            token = client.fetch_token(
                config.token_endpoint,
                grant_type="authorization_code",
                code=code,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC authorization code exchange failed") from exc
        if not isinstance(token, dict):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC token response must be a JSON object")
        return token

    def _validate_id_token(self, config: OIDCConfig, id_token: str, expected_nonce_hash: str) -> dict[str, Any]:
        jwks = self._fetch_jwks(config.jwks_uri)
        jwt = JsonWebToken(self.ALLOWED_ID_TOKEN_ALGS)
        try:
            claims = jwt.decode(
                id_token,
                JsonWebKey.import_key_set(jwks),
                claims_options={
                    "iss": {"essential": True, "values": [config.issuer_url.rstrip("/")]},
                    "aud": {"essential": True, "values": [config.client_id]},
                    "exp": {"essential": True},
                    "sub": {"essential": True},
                },
            )
            claims.validate(now=int(self.utcnow().timestamp()), leeway=60)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC id_token validation failed") from exc

        nonce = str(claims.get("nonce") or "")
        if not nonce or self._sha256(nonce) != expected_nonce_hash:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC id_token nonce validation failed")
        return dict(claims)

    def _fetch_jwks(self, jwks_uri: str) -> dict[str, Any]:
        try:
            assert_public_http_url(jwks_uri, field_name="jwks_uri")
        except UnsafeURLTargetError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to fetch OIDC JWKS") from exc
        try:
            response = httpx.get(jwks_uri, timeout=10.0, follow_redirects=False)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to fetch OIDC JWKS") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC JWKS must contain keys")
        return payload

    def _extract_email(self, claims: dict[str, Any], config: OIDCConfig) -> str | None:
        mapping = config.claim_mapping or {}
        email_claim = str(mapping.get("email") or "email")
        value = claims.get(email_claim)
        if isinstance(value, str) and "@" in value:
            return value.strip().lower()
        return None
