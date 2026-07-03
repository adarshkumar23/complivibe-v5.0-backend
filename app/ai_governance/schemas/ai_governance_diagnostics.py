from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class AIGovernanceDiagnosticGenerateRequest(BaseModel):
    business_unit_id: uuid.UUID | None = None
    snapshot_label: str | None = None


class AIGovernanceDiagnosticListItem(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID | None
    generated_by: uuid.UUID
    snapshot_label: str | None
    overall_governance_score: Decimal
    overall_health: Literal["good", "needs_attention", "at_risk", "critical"]
    ai_systems_assessed: int
    critical_gaps_count: int
    created_at: datetime


class AIGovernanceDiagnosticDetail(AIGovernanceDiagnosticListItem):
    snapshot_data: dict[str, Any]


class AIGovernanceDiagnosticListResponse(BaseModel):
    items: list[AIGovernanceDiagnosticListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
