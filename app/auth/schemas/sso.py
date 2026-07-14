import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Must match the DB check constraint ck_sso_configs_default_role (see
# app/models/sso_config.py). Validating here turns an out-of-range role into a
# clean 422 instead of a 500 IntegrityError at insert time.
ALLOWED_DEFAULT_ROLES = ("member", "reviewer", "compliance_manager", "admin", "owner", "auditor")


def _validate_default_role(value: str | None) -> str | None:
    if value is None:
        return value
    if value not in ALLOWED_DEFAULT_ROLES:
        raise ValueError(f"default_role must be one of: {', '.join(ALLOWED_DEFAULT_ROLES)}")
    return value


class SSOConfigCreate(BaseModel):
    provider: str
    entity_id: str
    sso_url: str
    slo_url: str | None = None
    certificate: str
    attribute_mapping: dict[str, Any] = Field(
        default_factory=lambda: {
            "email": "NameID",
            "first_name": "firstName",
            "last_name": "lastName",
            "role": "groups",
        }
    )
    jit_provisioning: bool = True
    default_role: str = "member"

    @field_validator("default_role")
    @classmethod
    def validate_default_role(cls, value: str) -> str:
        return _validate_default_role(value)


class SSOConfigUpdate(BaseModel):
    provider: str | None = None
    entity_id: str | None = None
    sso_url: str | None = None
    slo_url: str | None = None
    certificate: str | None = None
    attribute_mapping: dict[str, Any] | None = None
    jit_provisioning: bool | None = None
    default_role: str | None = None

    @field_validator("default_role")
    @classmethod
    def validate_default_role(cls, value: str | None) -> str | None:
        return _validate_default_role(value)


class SSOConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    entity_id: str
    sso_url: str
    slo_url: str | None
    attribute_mapping: dict[str, Any]
    is_active: bool
    jit_provisioning: bool
    default_role: str
    created_at: datetime


class SSOInitiateResponse(BaseModel):
    redirect_url: str


class SSOCallbackResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_method: str = "sso"


class SSOTestConfigResponse(BaseModel):
    valid: bool
    errors: list[str]
