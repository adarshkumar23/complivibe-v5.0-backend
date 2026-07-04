import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_OIDC_SCOPES = ["openid", "email", "profile"]
DEFAULT_OIDC_CLAIM_MAPPING = {"email": "email", "subject": "sub", "name": "name"}


def _normalize_issuer(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith("https://"):
        raise ValueError("OIDC issuer_url must use https")
    return value


def _normalize_https_url(value: str) -> str:
    value = value.strip()
    if not value.startswith("https://"):
        raise ValueError("OIDC endpoint URLs must use https")
    return value


class OIDCConfigCreate(BaseModel):
    provider: str = "oidc"
    issuer_url: str
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    jwks_uri: str | None = None
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_OIDC_SCOPES), min_length=1)
    claim_mapping: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_OIDC_CLAIM_MAPPING))
    jit_provisioning: bool = True
    default_role: str = "member"

    @field_validator("issuer_url")
    @classmethod
    def validate_issuer(cls, value: str) -> str:
        return _normalize_issuer(value)

    @field_validator("authorization_endpoint", "token_endpoint", "jwks_uri")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        return _normalize_https_url(value) if value else value

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        normalized = [scope.strip() for scope in value if scope.strip()]
        if "openid" not in normalized:
            raise ValueError("OIDC scopes must include openid")
        return normalized

    @field_validator("claim_mapping")
    @classmethod
    def validate_claim_mapping(cls, value: dict[str, Any]) -> dict[str, Any]:
        email_claim = str(value.get("email") or "").strip()
        subject_claim = str(value.get("subject") or "").strip()
        if not email_claim or not subject_claim:
            raise ValueError("OIDC claim_mapping must include email and subject")
        return {**dict(DEFAULT_OIDC_CLAIM_MAPPING), **value}


class OIDCConfigUpdate(BaseModel):
    provider: str | None = None
    issuer_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    jwks_uri: str | None = None
    scopes: list[str] | None = None
    claim_mapping: dict[str, Any] | None = None
    jit_provisioning: bool | None = None
    default_role: str | None = None

    @field_validator("issuer_url")
    @classmethod
    def validate_issuer(cls, value: str | None) -> str | None:
        return _normalize_issuer(value) if value else value

    @field_validator("authorization_endpoint", "token_endpoint", "jwks_uri")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        return _normalize_https_url(value) if value else value

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = [scope.strip() for scope in value if scope.strip()]
        if "openid" not in normalized:
            raise ValueError("OIDC scopes must include openid")
        return normalized

    @field_validator("claim_mapping")
    @classmethod
    def validate_claim_mapping(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        email_claim = str(value.get("email") or "").strip()
        subject_claim = str(value.get("subject") or "").strip()
        if not email_claim or not subject_claim:
            raise ValueError("OIDC claim_mapping must include email and subject")
        return {**dict(DEFAULT_OIDC_CLAIM_MAPPING), **value}


class OIDCConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    issuer_url: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    scopes: list[str]
    claim_mapping: dict[str, Any]
    is_active: bool
    jit_provisioning: bool
    default_role: str
    created_at: datetime


class OIDCInitiateResponse(BaseModel):
    redirect_url: str


class OIDCCallbackResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_method: str = "oidc"


class OIDCTestConfigResponse(BaseModel):
    valid: bool
    errors: list[str]
