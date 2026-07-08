from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

TEST_TYPE_PATTERN = "^(tabletop|simulation|threat_led_pen_test)$"
STATUS_PATTERN = "^(scheduled|in_progress|completed|cancelled)$"
SEVERITY_PATTERN = "^(critical|high|medium|low)$"


class ResilienceTestFinding(BaseModel):
    description: str = Field(min_length=1)
    severity: str = Field(pattern=SEVERITY_PATTERN)


class ResilienceTestResults(BaseModel):
    summary: str = ""
    findings: list[ResilienceTestFinding] = Field(default_factory=list)


class ResilienceTestCreate(BaseModel):
    test_type: str = Field(pattern=TEST_TYPE_PATTERN)
    scope: str = Field(min_length=1)
    scheduled_date: date
    owner_team: str | None = None


class ResilienceTestUpdate(BaseModel):
    scope: str | None = Field(default=None, min_length=1)
    scheduled_date: date | None = None
    owner_team: str | None = None
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class ResilienceTestCompleteRequest(BaseModel):
    results_json: ResilienceTestResults


class ResilienceTestRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    test_type: str = Field(pattern=TEST_TYPE_PATTERN)
    scope: str
    scheduled_date: date
    completed_date: date | None = None
    results_json: dict[str, Any] | None = None
    findings_count: int
    status: str = Field(pattern=STATUS_PATTERN)
    owner_team: str | None = None
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    context_flags: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ResilienceTestCompleteResponse(BaseModel):
    test: ResilienceTestRead
    issues_created: list[uuid.UUID]


class ResilienceTestOverdueStatus(BaseModel):
    test_type: str = Field(pattern=TEST_TYPE_PATTERN)
    is_overdue: bool
    reason: str
    last_completed_date: date | None = None
    next_due_date: date | None = None
