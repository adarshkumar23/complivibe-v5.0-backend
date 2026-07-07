import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineageNodeCreate(BaseModel):
    node_type: str
    data_asset_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    system_name: str | None = Field(default=None, max_length=255)


class LineageNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    node_type: str
    data_asset_id: uuid.UUID | None
    name: str
    description: str | None
    system_name: str | None
    created_at: datetime
    updated_at: datetime
    upstream_edge_count: int = 0
    downstream_edge_count: int = 0
    is_orphan: bool = False
    context_flags: list[str] = []


class LineageEdgeCreate(BaseModel):
    upstream_node_id: uuid.UUID
    downstream_node_id: uuid.UUID
    transformation_description: str | None = None
    pipeline_name: str | None = Field(default=None, max_length=255)
    pipeline_run_id: str | None = Field(default=None, max_length=255)
    job_name: str | None = Field(default=None, max_length=255)
    event_time: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    upstream_node_id: uuid.UUID
    downstream_node_id: uuid.UUID
    transformation_description: str | None
    source_method: str
    pipeline_name: str | None
    pipeline_run_id: str | None
    job_name: str | None
    event_time: datetime | None
    metadata_json: dict
    created_at: datetime


class LineageGraphNode(BaseModel):
    id: uuid.UUID
    name: str
    node_type: str


class LineageGraphEdge(BaseModel):
    upstream_id: uuid.UUID
    downstream_id: uuid.UUID
    source_method: str


class LineageGraphRead(BaseModel):
    asset_id: str
    nodes: list[LineageGraphNode]
    edges: list[LineageGraphEdge]
    node_count: int = 0
    edge_count: int = 0
    isolated_node_count: int = 0
    cycle_detected: bool = False
    stale_edge_count: int = 0
    context_flags: list[str] = []


class OpenMetadataConfigureRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    jwt_token: str = Field(min_length=1)
    org_api_key: str | None = Field(default=None, min_length=12, max_length=255)


class OpenMetadataStatusRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    base_url: str
    sync_status: str | None
    last_synced_at: datetime | None
    last_sync_error: str | None
    is_active: bool
    api_key_configured: bool


class OpenMetadataConfigureRead(OpenMetadataStatusRead):
    ingest_api_key: str | None = None


class OpenMetadataSyncRead(BaseModel):
    skipped: bool = False
    tables_seen: int = 0
    nodes_created: int = 0
    edges_created: int = 0


class OpenLineageEventResult(BaseModel):
    edges_created: int
    job_name: str
