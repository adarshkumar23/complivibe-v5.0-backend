import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.validation import InvalidChoiceError

SUPPORTED_MLOPS_INTEGRATION_TYPES = ("mlflow", "databricks", "sagemaker", "vertex_ai")


class MLOpsIntegrationCreate(BaseModel):
    integration_type: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    config_json: dict

    @field_validator("integration_type")
    @classmethod
    def _validate_integration_type(cls, value: str) -> str:
        if value not in SUPPORTED_MLOPS_INTEGRATION_TYPES:
            raise InvalidChoiceError(
                "integration_type",
                value,
                SUPPORTED_MLOPS_INTEGRATION_TYPES,
            )
        return value


class MLOpsIntegrationUpdate(BaseModel):
    integration_type: str | None = Field(default=None, min_length=2, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    config_json: dict | None = None
    is_active: bool | None = None

    @field_validator("integration_type")
    @classmethod
    def _validate_integration_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in SUPPORTED_MLOPS_INTEGRATION_TYPES:
            raise InvalidChoiceError(
                "integration_type",
                value,
                SUPPORTED_MLOPS_INTEGRATION_TYPES,
            )
        return value


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
