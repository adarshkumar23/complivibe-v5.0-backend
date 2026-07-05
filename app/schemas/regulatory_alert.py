from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RegulatoryChangeAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    source_key: str
    source_name: str
    source_url: str | None
    source_item_id: str
    framework_code: str | None
    title: str
    summary: str | None
    item_url: str | None
    published_at: datetime | None
    detected_at: datetime
    status: str
    severity: str
    match_reason: str | None
    raw_item_json: dict
    error_message: str | None
    acknowledged_at: datetime | None
    acknowledged_by_user_id: uuid.UUID | None
    impacted_obligation_count: int = 0
    impacted_open_obligation_count: int = 0
    impacted_control_count: int = 0
    impacted_obligation_samples: list[dict] = []
