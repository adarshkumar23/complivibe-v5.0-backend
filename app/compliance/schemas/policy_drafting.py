from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PolicyDraftCreateRequest(BaseModel):
    prompt: str = Field(min_length=5)
    business_unit_id: uuid.UUID | None = None


class PolicyDraftCreateResponse(BaseModel):
    id: uuid.UUID
    draft_output: str
    provider_used: str
    used_byo_credentials: bool
    status: str


class PolicyDraftAcceptRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    owner_user_id: uuid.UUID
    description: str | None = None
    review_due_date: datetime | None = None
    effective_date: datetime | None = None
    policy_type: str = "other"


class PolicyDraftRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID | None
    content_type: str
    prompt_input: str
    draft_output: str
    provider_used: str
    used_byo_credentials: bool
    status: str
    linked_policy_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PolicyDraftListResponse(BaseModel):
    items: list[PolicyDraftRead]
    total: int
    page: int
    page_size: int


class AICfgUpdateRequest(BaseModel):
    use_byo_credentials: bool = False
    groq_api_key: str | None = None
    azure_api_key: str | None = None
    azure_endpoint: str | None = None
    azure_deployment_name: str | None = None
    is_active: bool = True


class AICfgRead(BaseModel):
    id: uuid.UUID | None = None
    organization_id: uuid.UUID
    use_byo_credentials: bool
    is_active: bool
    groq_api_key_configured: bool
    azure_api_key_configured: bool
    azure_endpoint: str | None = None
    azure_deployment_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
