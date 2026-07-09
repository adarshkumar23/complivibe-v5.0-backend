from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ControlObligationMapRead(BaseModel):
    obligation_id: UUID
    mapping_type: str
    confidence: str
    status: str


class ControlCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    control_code: str | None = Field(default=None, max_length=120)
    control_type: str = Field(pattern="^(policy|technical|administrative|process|ai_governance|vendor|privacy|security)$")
    criticality: str = Field(pattern="^(low|medium|high|critical)$")
    owner_user_id: UUID | None = None
    testing_procedure: str | None = None
    implementation_notes: str | None = None


class ControlUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(not_started|in_progress|implemented|needs_review|failed|not_applicable|archived)$")
    criticality: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    owner_user_id: UUID | None = None
    testing_procedure: str | None = None
    implementation_notes: str | None = None


class ControlRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: str | None = None
    control_code: str | None = None
    control_type: str
    status: str
    criticality: str
    owner_user_id: UUID | None = None
    last_reviewed_at: datetime | None = None
    testing_procedure: str | None = None
    implementation_notes: str | None = None
    source: str
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    owner_membership_active: bool | None = None


class ControlDetail(ControlRead):
    mapped_obligations: list[ControlObligationMapRead]
    evidence_count: int
    active_exception: dict | None = None


class ControlObligationMapCreate(BaseModel):
    obligation_id: UUID
    mapping_type: str = Field(pattern="^(satisfies|partially_satisfies|supports|related)$")
    confidence: str = Field(default="manual_confirmed", pattern="^(manual_confirmed|system_suggested|imported|low_confidence)$")
    rationale: str | None = None


class ControlGapSummary(BaseModel):
    total_active_obligations: int
    obligations_with_controls: int
    obligations_without_controls: int
    controls_not_started: int
    controls_in_progress: int
    controls_implemented: int
    high_criticality_open_controls: int
