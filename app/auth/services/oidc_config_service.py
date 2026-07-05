from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas.oidc import OIDCConfigCreate, OIDCConfigUpdate
from app.core.url_security import UnsafeURLTargetError, assert_public_http_url, raise_unsafe_url_http_error
from app.models.oidc_config import OIDCConfig
from app.services.audit_service import AuditService
from app.services.secrets_service import SecretsService, legacy_key_from_fernet_secret_key


class OIDCConfigService:
    DISCOVERY_PATH = "/.well-known/openid-configuration"

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _secrets(self, organization_id: uuid.UUID) -> SecretsService:
        return SecretsService(
            self.db,
            organization_id=organization_id,
            legacy_key_resolver=legacy_key_from_fernet_secret_key,
        )

    def encrypt_secret(self, value: str, *, organization_id: uuid.UUID, entity_id: uuid.UUID | None = None) -> str:
        return self._secrets(organization_id).encrypt(value, secret_name="oidc_client_secret", entity_id=entity_id)

    def decrypt_secret(self, value: str, *, organization_id: uuid.UUID, entity_id: uuid.UUID | None = None) -> str:
        return self._secrets(organization_id).decrypt(value, secret_name="oidc_client_secret", entity_id=entity_id)

    def create_config(
        self,
        org_id: uuid.UUID,
        data: OIDCConfigCreate,
        created_by: uuid.UUID,
        db: Session,
    ) -> OIDCConfig:
        existing = db.execute(
            select(OIDCConfig).where(
                OIDCConfig.organization_id == org_id,
                OIDCConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="OIDC config already exists for this org. Update the existing config.",
            )

        payload = data.model_dump()
        endpoints = self._resolve_endpoints(payload)
        self._validate_https_endpoints(endpoints)

        config = OIDCConfig(
            organization_id=org_id,
            provider=payload["provider"],
            issuer_url=payload["issuer_url"],
            client_id=payload["client_id"],
            client_secret_enc=self.encrypt_secret(payload["client_secret"], organization_id=org_id),
            authorization_endpoint=endpoints["authorization_endpoint"],
            token_endpoint=endpoints["token_endpoint"],
            jwks_uri=endpoints["jwks_uri"],
            scopes=payload["scopes"],
            claim_mapping=payload["claim_mapping"],
            jit_provisioning=payload["jit_provisioning"],
            default_role=payload["default_role"],
            created_by=created_by,
        )
        db.add(config)
        db.flush()

        AuditService(db).write_audit_log(
            action="oidc_config.created",
            entity_type="oidc_configs",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=config.id,
            after_json={"provider": config.provider, "issuer_url": config.issuer_url, "client_id": config.client_id},
        )
        return config

    def get_config(self, org_id: uuid.UUID, db: Session) -> OIDCConfig:
        config = db.execute(
            select(OIDCConfig).where(
                OIDCConfig.organization_id == org_id,
                OIDCConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC config not found")
        return config

    def update_config(
        self,
        org_id: uuid.UUID,
        config_id: uuid.UUID,
        data: OIDCConfigUpdate,
        user_id: uuid.UUID,
        db: Session,
    ) -> OIDCConfig:
        config = self._require_config(org_id, config_id, db)
        payload = data.model_dump(exclude_unset=True)
        if not payload:
            return config

        effective = {
            "issuer_url": config.issuer_url,
            "authorization_endpoint": config.authorization_endpoint,
            "token_endpoint": config.token_endpoint,
            "jwks_uri": config.jwks_uri,
        }
        for key in effective:
            if key in payload:
                effective[key] = payload[key]
        endpoints = self._resolve_endpoints(effective)
        self._validate_https_endpoints(endpoints)

        for key, value in payload.items():
            if key == "client_secret":
                config.client_secret_enc = self.encrypt_secret(value, organization_id=org_id, entity_id=config.id)
            elif key in {"authorization_endpoint", "token_endpoint", "jwks_uri"}:
                setattr(config, key, endpoints[key])
            else:
                setattr(config, key, value)

        if any(key in payload for key in {"issuer_url", "authorization_endpoint", "token_endpoint", "jwks_uri"}):
            config.authorization_endpoint = endpoints["authorization_endpoint"]
            config.token_endpoint = endpoints["token_endpoint"]
            config.jwks_uri = endpoints["jwks_uri"]

        config.updated_at = self.utcnow()
        db.flush()

        AuditService(db).write_audit_log(
            action="oidc_config.updated",
            entity_type="oidc_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
            after_json={"provider": config.provider, "issuer_url": config.issuer_url, "client_id": config.client_id},
        )
        return config

    def activate_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> OIDCConfig:
        config = self._require_config(org_id, config_id, db)
        self._validate_https_endpoints(
            {
                "authorization_endpoint": config.authorization_endpoint,
                "token_endpoint": config.token_endpoint,
                "jwks_uri": config.jwks_uri,
            }
        )
        config.is_active = True
        config.updated_at = self.utcnow()
        db.flush()
        AuditService(db).write_audit_log(
            action="oidc_config.activated",
            entity_type="oidc_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )
        return config

    def deactivate_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> OIDCConfig:
        config = self._require_config(org_id, config_id, db)
        config.is_active = False
        config.updated_at = self.utcnow()
        db.flush()
        AuditService(db).write_audit_log(
            action="oidc_config.deactivated",
            entity_type="oidc_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )
        return config

    def soft_delete_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
        config = self._require_config(org_id, config_id, db)
        now = self.utcnow()
        config.deleted_at = now
        config.is_active = False
        config.updated_at = now
        db.flush()
        AuditService(db).write_audit_log(
            action="oidc_config.deleted",
            entity_type="oidc_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )

    def test_config(self, org_id: uuid.UUID, config_id: uuid.UUID, db: Session) -> tuple[bool, list[str]]:
        config = self._require_config(org_id, config_id, db)
        errors: list[str] = []
        if not config.issuer_url.startswith("https://"):
            errors.append("issuer_url must use https")
        for field_name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            value = str(getattr(config, field_name) or "")
            if not value.startswith("https://"):
                errors.append(f"{field_name} must use https")
        if "openid" not in (config.scopes or []):
            errors.append("scopes must include openid")
        mapping = config.claim_mapping or {}
        if not mapping.get("email") or not mapping.get("subject"):
            errors.append("claim_mapping must include email and subject")
        return len(errors) == 0, errors

    def _require_config(self, org_id: uuid.UUID, config_id: uuid.UUID, db: Session) -> OIDCConfig:
        config = db.execute(
            select(OIDCConfig).where(
                OIDCConfig.organization_id == org_id,
                OIDCConfig.id == config_id,
                OIDCConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC config not found")
        return config

    def _resolve_endpoints(self, payload: dict[str, Any]) -> dict[str, str]:
        endpoints = {
            "authorization_endpoint": payload.get("authorization_endpoint"),
            "token_endpoint": payload.get("token_endpoint"),
            "jwks_uri": payload.get("jwks_uri"),
        }
        if all(endpoints.values()):
            return {key: str(value) for key, value in endpoints.items()}

        discovery = self._fetch_discovery_document(str(payload["issuer_url"]))
        issuer = str(discovery.get("issuer") or "").rstrip("/")
        if issuer and issuer != str(payload["issuer_url"]).rstrip("/"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OIDC discovery issuer mismatch")
        resolved = {
            "authorization_endpoint": endpoints["authorization_endpoint"] or discovery.get("authorization_endpoint"),
            "token_endpoint": endpoints["token_endpoint"] or discovery.get("token_endpoint"),
            "jwks_uri": endpoints["jwks_uri"] or discovery.get("jwks_uri"),
        }
        missing = [key for key, value in resolved.items() if not value]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"OIDC discovery missing required fields: {', '.join(missing)}",
            )
        return {key: str(value) for key, value in resolved.items()}

    def _fetch_discovery_document(self, issuer_url: str) -> dict[str, Any]:
        url = issuer_url.rstrip("/") + self.DISCOVERY_PATH
        try:
            assert_public_http_url(url, field_name="issuer_url")
        except UnsafeURLTargetError as exc:
            raise_unsafe_url_http_error(exc, field_name="issuer_url")
        try:
            response = httpx.get(url, timeout=10.0, follow_redirects=False)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unable to fetch OIDC discovery document") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OIDC discovery document must be a JSON object")
        return payload

    def _validate_https_endpoints(self, endpoints: dict[str, str]) -> None:
        for field_name, value in endpoints.items():
            if not str(value).startswith("https://"):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must use https")
