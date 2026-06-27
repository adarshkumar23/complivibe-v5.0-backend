import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MLOpsIntegrationCreate(BaseModel):
    integration_type: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    config_json: dict


class MLOpsIntegrationUpdate(BaseModel):
    integration_type: str | None = Field(default=None, min_length=2, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    config_json: dict | None = None
    is_active: bool | None = None


class MLOpsIntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    integration_type: str
    name: str
    last_synced_at: datetime | None
    sync_status: str | None
    last_sync_error: str | None
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class MLOpsSyncResult(BaseModel):
    models_found: int
    systems_created: int
    aiboms_updated: int


class MLOpsSyncLogRead(BaseModel):
    id: uuid.UUID
    sync_status: str | None
    last_synced_at: datetime | None
    last_sync_error: str | None
