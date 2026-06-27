import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationPreferenceUpdate(BaseModel):
    channel: str
    is_enabled: bool
    min_severity: str | None = None


class NotificationPreferenceBulkUpdate(BaseModel):
    updates: list[dict]


class NotificationPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    channel: str
    min_severity: str | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
