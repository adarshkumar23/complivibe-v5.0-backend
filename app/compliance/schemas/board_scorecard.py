from __future__ import annotations

import uuid
from datetime import datetime, date

from pydantic import BaseModel, Field


class BoardScorecardGenerateRequest(BaseModel):
    business_unit_id: uuid.UUID | None = None
    snapshot_label: str | None = Field(default=None, max_length=200)


class BoardScorecardListItem(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID | None
    generated_by: uuid.UUID
    snapshot_label: str | None
    overall_compliance_score: float
    created_at: datetime


class BoardScorecardDetail(BoardScorecardListItem):
    snapshot_data: dict


class BoardScorecardListResponse(BaseModel):
    items: list[BoardScorecardListItem]
    page: int
    page_size: int
    total: int


class BoardScorecardListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    business_unit_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
