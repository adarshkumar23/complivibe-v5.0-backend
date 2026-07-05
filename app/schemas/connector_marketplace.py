from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConnectorCatalogCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=80)
    description: str | None = None
    config_schema: dict = Field(default_factory=dict)
    enabled: bool = True


class ConnectorCatalogUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    config_schema: dict | None = None
    enabled: bool | None = None


class ConnectorCatalogRead(BaseModel):
    id: UUID
    name: str
    category: str
    description: str | None
    config_schema: dict
    enabled: bool
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}


class ConnectorEnableRequest(BaseModel):
    config_values_json: dict | None = None


class ConnectorOrgEnablementRead(BaseModel):
    id: UUID
    organization_id: UUID
    connector_id: UUID
    enabled: bool
    config_values_json: dict | None
    connection_status: str
    connection_checked_at: datetime | None
    connection_error: str | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    connector: ConnectorCatalogRead
