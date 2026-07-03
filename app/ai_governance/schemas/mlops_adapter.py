from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MLflowConnectionCreate(BaseModel):
    connection_name: str = Field(min_length=1, max_length=150)
    tracking_server_url: str | None = Field(default=None, max_length=500)


class MLflowConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    connection_name: str
    tracking_server_url: str | None
    is_active: bool
    has_ingest_token: bool
    created_at: datetime
    updated_at: datetime


class MLflowConnectionCreateResponse(MLflowConnectionRead):
    ingest_token: str


class MLflowConnectionRotateResponse(BaseModel):
    id: uuid.UUID
    ingest_token: str


class MLflowIngestPayload(BaseModel):
    event_type: str
    model_name: str
    model_version: str | None = None
    stage: str | None = None
    run_id: str | None = None
    ai_system_id: uuid.UUID | None = None
    metrics: dict[str, Any] | None = None
    tags: dict[str, Any] | None = None
    registered_at: datetime | None = None
    drift_metric: str | None = None
    drift_value: Decimal | None = None
    drift_threshold: Decimal | None = None
    drift_context: dict[str, Any] | None = None


class MLflowModelRegistrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    mlflow_connection_id: uuid.UUID
    ai_system_id: uuid.UUID | None
    model_name: str
    model_version: str
    stage: str
    run_id: str | None
    metrics_json: dict[str, Any] | None
    tags_json: dict[str, Any] | None
    event_type: str
    registered_at: datetime
    compliance_status: str
    auto_linked: bool
    created_at: datetime


class MLflowDriftEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    mlflow_connection_id: uuid.UUID
    ai_system_id: uuid.UUID | None
    mlflow_model_registration_id: uuid.UUID | None
    model_name: str
    model_version: str | None
    drift_metric: str
    drift_value: Decimal
    drift_threshold: Decimal | None
    severity: str
    drift_context_json: dict[str, Any] | None
    auto_risk_created: bool
    linked_risk_id: uuid.UUID | None
    detected_at: datetime
    created_at: datetime


class MLflowManualLinkRequest(BaseModel):
    ai_system_id: uuid.UUID


class MLflowComplianceStatusRequest(BaseModel):
    status: str = Field(pattern="^(reviewed|approved|flagged)$")
