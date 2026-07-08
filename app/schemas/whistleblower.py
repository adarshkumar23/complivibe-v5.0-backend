from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

CATEGORY_PATTERN = (
    "^(fraud|corruption|harassment|safety_violation|data_privacy|financial_misconduct|"
    "discrimination|retaliation|other)$"
)
STATUS_PATTERN = "^(submitted|under_review|investigating|resolved|closed|dismissed)$"
MAX_DESCRIPTION_LENGTH = 10_000
MAX_MESSAGE_LENGTH = 10_000


class WhistleblowerReportSubmitRequest(BaseModel):
    organization_id: uuid.UUID
    category: str = Field(pattern=CATEGORY_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)


class WhistleblowerReportSubmitResponse(BaseModel):
    tracking_code: str
    anonymous_id: str
    warning: str = "This tracking code is shown only once. Save it securely -- it is the only way to check your report's status."


class WhistleblowerReporterMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class WhistleblowerInvestigatorMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class WhistleblowerStatusUpdateRequest(BaseModel):
    status: str = Field(pattern=STATUS_PATTERN)
    resolution_summary: str | None = None


class WhistleblowerMessageRead(BaseModel):
    id: uuid.UUID
    sender_type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WhistleblowerReporterStatusRead(BaseModel):
    """Reporter-visible view -- no investigator identity or internal-only fields."""

    anonymous_id: str
    category: str
    status: str
    created_at: datetime
    messages: list[WhistleblowerMessageRead]


class WhistleblowerReportRead(BaseModel):
    """Investigator (internal) view."""

    id: uuid.UUID
    organization_id: uuid.UUID
    anonymous_id: str
    category: str
    description: str
    status: str
    assigned_investigator_user_id: uuid.UUID | None = None
    resolution_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    days_open: int = 0
    context_flags: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WhistleblowerReportDetailRead(WhistleblowerReportRead):
    messages: list[WhistleblowerMessageRead]
