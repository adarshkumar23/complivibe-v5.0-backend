from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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


class ComplianceTimelineEvent(BaseModel):
    event_key: str
    event_type: str
    occurred_at: datetime
    entity_type: str
    entity_id: uuid.UUID
    title: str
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceTimelineResponse(BaseModel):
    total_events: int
    has_more: bool = Field(
        default=False,
        description=(
            "True if additional matching events exist beyond what is returned in `events` -- "
            "either because the merged result set exceeded `limit`, or because one of the "
            "underlying per-source queries itself hit `limit` (so its own tail may be missing)."
        ),
    )
    events: list[ComplianceTimelineEvent]


class ComplianceInboxItem(BaseModel):
    item_key: str
    item_type: str
    title: str
    detail: str | None = None
    reason: str | None = Field(
        default=None,
        description="Short explanation of why this item is prioritized where it is (e.g. days overdue).",
    )
    priority_score: int
    due_at: datetime | None = None
    navigate_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceInboxResponse(BaseModel):
    total_items: int
    items: list[ComplianceInboxItem]


class ComplianceSummaryGenerateRequest(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=24 * 90)
    max_views: int | None = Field(default=None, ge=1, le=100000)
    password: str | None = Field(default=None, max_length=255)
    recipient_email: str | None = Field(default=None, max_length=255)
    watermark_text: str | None = Field(default=None, max_length=255)
    brand_name: str | None = Field(default=None, max_length=120)
    include_sections: list[str] = Field(default_factory=lambda: ["overview", "controls", "evidence", "risks", "deadlines"])


class ComplianceSummaryGenerateResponse(BaseModel):
    share_id: uuid.UUID
    token: str
    public_url: str
    expires_at: datetime
    password_protected: bool
    expires_in_hours: float
    max_views: int | None = None
    context_flags: list[str] = Field(default_factory=list)
