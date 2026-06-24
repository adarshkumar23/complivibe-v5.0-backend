from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ControlTestDefinitionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    test_type: str = Field(pattern="^(manual_attestation|internal_metadata_check|evidence_review_check)$")
    check_key: str
    cadence: str = Field(default="none", pattern="^(none|weekly|monthly|quarterly|annual)$")
    next_due_at: datetime | None = None
    owner_user_id: UUID | None = None
    metadata_json: dict | None = None


class ControlTestDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")
    cadence: str | None = Field(default=None, pattern="^(none|weekly|monthly|quarterly|annual)$")
    next_due_at: datetime | None = None
    owner_user_id: UUID | None = None
    metadata_json: dict | None = None


class ControlTestDefinitionRead(BaseModel):
    id: UUID
    organization_id: UUID
    control_id: UUID
    name: str
    description: str | None = None
    test_type: str
    check_key: str
    status: str
    cadence: str
    next_due_at: datetime | None = None
    last_run_at: datetime | None = None
    owner_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ControlTestRunCreateRequest(BaseModel):
    manual_result: str | None = Field(default=None, pattern="^(passed|failed|needs_review|not_applicable)$")
    result_reason: str | None = None
    evidence_item_id: UUID | None = None
    dry_run: bool = False


class ControlTestRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    control_test_definition_id: UUID
    control_id: UUID
    result: str
    result_reason: str | None = None
    check_key: str
    executed_by_user_id: UUID | None = None
    execution_source: str
    evidence_item_id: UUID | None = None
    metadata_json: dict | None = None
    created_at: datetime


class ControlTestRunResponse(BaseModel):
    dry_run: bool
    run: ControlTestRunRead | None = None
    computed_result: str
    computed_reason: str | None = None


class ControlTestingSummary(BaseModel):
    active_tests: int
    tests_due: int
    tests_overdue: int
    latest_passed: int
    latest_failed: int
    latest_needs_review: int
    controls_without_tests: int
