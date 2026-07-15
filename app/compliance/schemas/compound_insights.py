from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CompoundInsightRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    pattern_id: str
    severity: str
    status: str
    title: str
    templated_narrative: str
    narrative_source: str
    narrative_headline: str | None
    narrative_summary: str | None
    recommended_actions_json: list[Any] | None
    matched_nodes_json: dict[str, Any]
    provider_used: str | None
    detection_count: int
    first_detected_at: datetime
    last_detected_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompoundInsightListResponse(BaseModel):
    items: list[CompoundInsightRead]
    total: int
    page: int
    page_size: int
