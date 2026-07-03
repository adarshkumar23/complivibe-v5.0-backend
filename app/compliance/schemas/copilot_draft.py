from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DraftRefineRequest(BaseModel):
    refinement_instruction: str = Field(min_length=3)


class DraftRefineResponse(BaseModel):
    draft_id: uuid.UUID
    revision_id: uuid.UUID
    revision_number: int
    revised_output: str
    provider_used: str
    used_byo_credentials: bool


class DraftRevisionRead(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    organization_id: uuid.UUID
    revision_number: int
    refinement_instruction: str
    revised_output: str
    provider_used: str
    used_byo_credentials: bool
    created_by: uuid.UUID
    created_at: datetime


class InlineSuggestRequest(BaseModel):
    content_type: Literal["policy", "control", "risk"]
    source_text: str = Field(min_length=5)
    linked_entity_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None


class InlineSuggestResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID | None
    content_type: str
    suggestions_json: list[dict]
    provider_used: str
    used_byo_credentials: bool
    status: str
    created_at: datetime


class SuggestionStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
