from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

PBC_STATUS_PATTERN = "^(pending|submitted|accepted|rejected|overdue)$"


class PbcItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    assignee_id: UUID | None = None
    due_date: date


class PbcItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    assignee_id: UUID | None = None
    due_date: date | None = None


class PbcSubmitRequest(BaseModel):
    evidence_id: UUID | None = None


class PbcRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1)


class PbcAcceptRequest(BaseModel):
    # Required only when the item has no evidence attached; the service enforces
    # that at least one of (evidence present, override_reason) holds.
    override_reason: str | None = Field(default=None, min_length=1)


class PbcItemRead(UUIDTimestampSchema):
    organization_id: UUID
    audit_engagement_id: UUID
    title: str
    description: str | None = None
    requester_id: UUID
    assignee_id: UUID | None = None
    due_date: date
    status: str = Field(pattern=PBC_STATUS_PATTERN)
    evidence_id: UUID | None = None
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    days_overdue: int = 0
    fieldwork_deadline: date | None = None
    overdue_relative_to_fieldwork_deadline: bool = False
    days_past_fieldwork_deadline: int = 0
    acceptance_override_reason: str | None = None


class PbcSummary(BaseModel):
    total_items: int
    by_status: dict[str, int]
    overdue_count: int
    completion_rate: float
    items_without_evidence: int
    avg_days_to_submit: float | None = None
