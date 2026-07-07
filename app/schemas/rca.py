from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RCABase(BaseModel):
    summary: str = Field(min_length=1)
    timeline_description: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    contributing_factors: list[str] = Field(default_factory=list)
    corrective_actions: list[str] = Field(default_factory=list)
    preventive_measures: list[str] = Field(default_factory=list)


class RCACreate(RCABase):
    pass


class RCAUpdate(BaseModel):
    summary: str | None = Field(default=None, min_length=1)
    timeline_description: str | None = Field(default=None, min_length=1)
    root_cause: str | None = Field(default=None, min_length=1)
    contributing_factors: list[str] | None = None
    corrective_actions: list[str] | None = None
    preventive_measures: list[str] | None = None


class RCARead(RCABase):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    authored_by: UUID
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    severity_at_creation: str | None = None
    # True when the linked issue's severity has changed since this RCA was
    # authored -- the findings/timeline may no longer reflect the actual
    # blast radius of the (re-triaged) issue.
    severity_changed_since_rca: bool = False
