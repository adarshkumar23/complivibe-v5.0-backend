from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


SOURCE_PATTERN = "^(vanta|drata|sprinto|scrut|generic)$"
STATUS_PATTERN = "^(queued|processing|preview_ready|completed|failed)$"
CONFLICT_PATTERN = "^(skip|update)$"


class ImportJobCreateRequest(BaseModel):
    dry_run: bool = True
    conflict_strategy: str = Field(default="skip", pattern=CONFLICT_PATTERN)
    csv_content: str | None = None
    records: list[dict[str, Any]] | None = None
    source_payload: dict[str, Any] | None = None


class ImportJobRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    source_tool: str = Field(pattern=SOURCE_PATTERN)
    status: str = Field(pattern=STATUS_PATTERN)
    progress_current: int
    progress_total: int
    dry_run: bool
    conflict_strategy: str = Field(pattern=CONFLICT_PATTERN)
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ImportProgressRead(BaseModel):
    job: ImportJobRead
    result_json: dict[str, Any] | None = None


class ImportDryRunPreviewRead(BaseModel):
    job_id: uuid.UUID
    status: str = Field(pattern=STATUS_PATTERN)
    parsed_rows: int
    row_errors: list[dict[str, Any]]
    would_create: dict[str, int]
    would_update: dict[str, int]
    would_skip: dict[str, int]


class ImportCommitRead(BaseModel):
    job_id: uuid.UUID
    status: str = Field(pattern=STATUS_PATTERN)
    created: dict[str, int]
    updated: dict[str, int]
    skipped: dict[str, int]
    row_errors: list[dict[str, Any]]


class ImportParityModuleRead(BaseModel):
    entity_type: str = Field(pattern="^(control|evidence|policy|business_unit)$")
    expected_count: int
    imported_count: int
    verified_count: int
    parity_pct: float


class ImportParityBySourceRead(BaseModel):
    tool_source: str = Field(pattern=SOURCE_PATTERN)
    modules: list[ImportParityModuleRead]
    expected_count: int
    imported_count: int
    verified_count: int
    parity_pct: float


class ImportParityDashboardRead(BaseModel):
    threshold_pct: float
    ready_to_switch: bool
    overall: dict[str, Any]
    modules: list[ImportParityModuleRead]
    by_source: list[ImportParityBySourceRead]
