import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataAccessEventIngest(BaseModel):
    data_asset_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_external: str | None = Field(default=None, max_length=255)
    access_type: str
    access_result: str
    source_ip: str | None = Field(default=None, max_length=45)
    source_country: str | None = Field(default=None, min_length=2, max_length=2)
    bytes_transferred: int | None = None
    row_count: int | None = None
    session_id: str | None = Field(default=None, max_length=255)
    access_time: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataAccessLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    data_asset_id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_external: str | None
    access_type: str
    access_result: str
    source_ip: str | None
    source_country: str | None
    bytes_transferred: int | None
    row_count: int | None
    session_id: str | None
    access_time: datetime
    created_at: datetime
    metadata_json: dict


class DataAccessSummaryRead(BaseModel):
    total_accesses_7d: int
    by_access_type: dict[str, int]
    by_access_result: dict[str, int]
    unique_actors: int
    anomalies_detected: int


class DataAccessAnomalyRuleCreate(BaseModel):
    data_asset_id: uuid.UUID | None = None
    rule_type: str
    rule_config: dict[str, Any] = Field(default_factory=dict)


class DataAccessAnomalyRuleUpdate(BaseModel):
    rule_config: dict[str, Any] | None = None
    is_active: bool | None = None


class DataAccessAnomalyRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    data_asset_id: uuid.UUID | None
    rule_type: str
    rule_config: dict
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
