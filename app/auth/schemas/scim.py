import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ScimTokenCreate(BaseModel):
    description: str
    expires_at: datetime | None = None


class ScimTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class ScimTokenCreatedResponse(ScimTokenResponse):
    raw_token: str
    warning: str


class ScimPatchOperation(BaseModel):
    op: str
    path: str | None = None
    value: Any = None


class ScimPatchRequest(BaseModel):
    schemas: list[str]
    Operations: list[ScimPatchOperation]
