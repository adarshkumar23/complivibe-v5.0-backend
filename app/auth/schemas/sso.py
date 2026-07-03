import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class SSOConfigUpdate(BaseModel):
    provider: str | None = None
    entity_id: str | None = None
    sso_url: str | None = None
    slo_url: str | None = None
    certificate: str | None = None
    attribute_mapping: dict[str, Any] | None = None
    jit_provisioning: bool | None = None
    default_role: str | None = None


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
