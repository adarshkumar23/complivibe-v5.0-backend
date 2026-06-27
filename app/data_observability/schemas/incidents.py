import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataIncidentCreate(BaseModel):
    data_asset_id: uuid.UUID
    detector_type: str = "manual"
    detector_ref_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    severity: str
    rule_type: str | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    detected_by: str = "manual"


class DataIncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    data_asset_id: uuid.UUID
    detector_type: str
    detector_ref_id: uuid.UUID | None
    title: str
    description: str
    severity: str
    status: str
    rule_type: str | None
    evidence_json: dict
    linked_issue_id: uuid.UUID | None
    detected_by: str
    detected_at: datetime
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResolveIncidentRequest(BaseModel):
    notes: str | None = None


class DataIncidentSummaryRead(BaseModel):
    total: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    by_detector_type: dict[str, int]
    new_count: int
    auto_escalated_count: int
    assets_with_active_incidents: int


class EscalateIncidentRead(BaseModel):
    issue_id: uuid.UUID
    incident_id: uuid.UUID
