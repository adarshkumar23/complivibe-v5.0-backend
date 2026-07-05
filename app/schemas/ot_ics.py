from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

ASSET_TYPE_PATTERN = "^(plc|scada|hmi|rtu|historian|ics_gateway|sensor|actuator|other)$"
CRITICALITY_PATTERN = "^(low|medium|high|critical)$"
ASSET_STATUS_PATTERN = "^(active|decommissioned|under_maintenance)$"
FINDING_TYPE_PATTERN = "^(unpatched_firmware|default_credentials|unauthorized_network_bridge|anomalous_traffic|protocol_violation|other)$"
SEVERITY_PATTERN = "^(low|medium|high|critical)$"


# --- Agents ---


class OtIcsAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class OtIcsAgentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    is_active: bool
    last_seen_at: datetime | None = None
    created_at: datetime


class OtIcsAgentRegistrationResponse(OtIcsAgentResponse):
    token: str


# --- Assets ---


class OtIcsAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(pattern=ASSET_TYPE_PATTERN)
    network_segment: str | None = Field(default=None, max_length=100)
    criticality: str = Field(pattern=CRITICALITY_PATTERN)
    linked_data_asset_id: UUID | None = None
    status: str = Field(default="active", pattern=ASSET_STATUS_PATTERN)
    description: str | None = None


class OtIcsAssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: str | None = Field(default=None, pattern=ASSET_TYPE_PATTERN)
    network_segment: str | None = Field(default=None, max_length=100)
    criticality: str | None = Field(default=None, pattern=CRITICALITY_PATTERN)
    linked_data_asset_id: UUID | None = None
    status: str | None = Field(default=None, pattern=ASSET_STATUS_PATTERN)
    description: str | None = None


class OtIcsAssetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    asset_type: str
    network_segment: str | None = None
    criticality: str
    linked_data_asset_id: UUID | None = None
    status: str
    description: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# --- Findings ---


class OtIcsFindingIngestRequest(BaseModel):
    asset_id: UUID
    finding_type: str = Field(pattern=FINDING_TYPE_PATTERN)
    severity: str = Field(pattern=SEVERITY_PATTERN)
    description: str | None = None
    raw_payload: dict | None = None
    detected_at: datetime | None = None


class OtIcsFindingResponse(BaseModel):
    id: UUID
    organization_id: UUID
    asset_id: UUID
    agent_id: UUID | None = None
    finding_type: str
    severity: str
    description: str | None = None
    raw_payload: dict | None = None
    detected_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime


class OtIcsFindingIngestResponse(BaseModel):
    finding_id: UUID
    asset_id: UUID
    severity: str
    finding_type: str
    detected_at: datetime


class OtIcsAssetSegmentConcentration(BaseModel):
    network_segment: str
    open_high_or_critical_count: int


class OtIcsFindingSummaryResponse(BaseModel):
    total_findings: int
    open_findings: int
    resolved_findings: int
    counts_by_severity: dict[str, int]
    counts_by_finding_type: dict[str, int]
    assets_with_open_high_or_critical: list[UUID]
    flagged_network_segments: list[OtIcsAssetSegmentConcentration]
