from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CommandPaletteItem(BaseModel):
    item_type: str = Field(description="entity or action")
    action_key: str
    label: str
    subtitle: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    navigate_path: str | None = None
    payload_hint: dict = Field(default_factory=dict)


class CommandPaletteQueryResponse(BaseModel):
    query: str
    items: list[CommandPaletteItem]
    took_ms: int


class CommandPaletteExecuteRequest(BaseModel):
    action_key: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class CommandPaletteExecuteResponse(BaseModel):
    action_key: str
    status: str
    navigate_path: str | None = None
    task_id: uuid.UUID | None = None
    executed_at: datetime
