import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShadowAIReportCreate(BaseModel):
    detected_name: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class ShadowAIDetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    detected_name: str
    detection_method: str
    confidence: str
    status: str
    detected_at: datetime
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    notes: str | None
    registered_system_id: uuid.UUID | None
    reported_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ShadowAIReviewRequest(BaseModel):
    pass


class ShadowAIDismissRequest(BaseModel):
    notes: str | None = None
