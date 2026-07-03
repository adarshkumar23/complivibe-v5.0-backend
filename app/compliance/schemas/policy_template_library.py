from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PolicyTemplateCreateRequest(BaseModel):
    title: str
    description: str | None = None
    policy_type: str | None = None
    content: str = Field(min_length=20)


class PolicyTemplateApplyRequest(BaseModel):
    override_title: str | None = None


class PolicyTemplateResponse(BaseModel):
    id: UUID
    organization_id: UUID | None
    title: str
    description: str | None
    policy_type: str | None
    content: str
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PolicyTemplateApplyResponse(BaseModel):
    policy_id: UUID
    title: str
    status: str
