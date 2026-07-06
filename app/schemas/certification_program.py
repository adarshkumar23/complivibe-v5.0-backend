from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import UUIDTimestampSchema


class CertificationProgramRead(UUIDTimestampSchema):
    name: str
    target_framework: str
    duration_weeks: int
    weeks_json: list[dict]
    prerequisites_json: dict | list
    evidence_templates_json: list[dict]
    description: str | None = None
    status: str


class CertificationProgramActivateRequest(BaseModel):
    owner_user_id: UUID | None = None


class CertificationProgramActivateResponse(BaseModel):
    activation_id: UUID
    certification_program_id: UUID
    created_tasks: int
    created_evidence_requests: int
    created_deadlines: int
    projected_completion_date: date | None = None
    status: str


class CertificationProgramWeekProgress(BaseModel):
    week_number: int
    total_items: int
    completed_items: int
    completion_pct: float
    blockers: list[str]


class CertificationProgramProgressResponse(BaseModel):
    certification_program_id: UUID
    activation_id: UUID
    status: str
    activated_at: datetime
    projected_completion_date: date | None = None
    overall_completion_pct: float
    projected_on_track: bool
    blockers: list[str]
    weekly_progress: list[CertificationProgramWeekProgress]
