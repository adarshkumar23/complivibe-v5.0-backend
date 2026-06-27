from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

SLA_SEVERITY_PATTERN = "^(critical|high|medium|low)$"


class IssueSLAStatusRead(BaseModel):
    issue_id: UUID
    severity: str = Field(pattern=SLA_SEVERITY_PATTERN)
    response_deadline: datetime
    resolution_deadline: datetime
    response_met_at: datetime | None = None
    resolution_met_at: datetime | None = None
    response_breached: bool
    resolution_breached: bool
    response_sla_hours: int
    resolution_sla_hours: int
    response_remaining_hours: float | None = None
    resolution_remaining_hours: float | None = None


class IssueSLABreachRead(BaseModel):
    issue_id: UUID
    title: str
    severity: str = Field(pattern=SLA_SEVERITY_PATTERN)
    status: str
    owner_id: UUID
    response_deadline: datetime
    resolution_deadline: datetime
    response_breached: bool
    resolution_breached: bool
    response_met_at: datetime | None = None
    resolution_met_at: datetime | None = None


class IssueSLAPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    severity: str = Field(pattern=SLA_SEVERITY_PATTERN)
    response_sla_hours: int
    resolution_sla_hours: int
    created_at: datetime
    updated_at: datetime


class IssueSLAPolicyUpsertRequest(BaseModel):
    severity: str = Field(pattern=SLA_SEVERITY_PATTERN)
    response_hours: int = Field(ge=1)
    resolution_hours: int = Field(ge=1)


class SLABreachCheckResult(BaseModel):
    response_breached: int
    resolution_breached: int
    notifications_queued: int
