from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PolicyTemplateListResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str
    category: str
    framework_tags: list[str]
    version: str
    is_active: bool
    created_at: datetime
    clone_count: int


class PolicyTemplateDetailResponse(PolicyTemplateListResponse):
    content: str


class PolicyTemplateCloneRequest(BaseModel):
    policy_name: str | None = Field(default=None, min_length=1, max_length=255)
    customization_notes: str | None = None


class PolicyTemplateSummary(BaseModel):
    id: UUID
    slug: str
    name: str
    category: str


class PolicySummary(BaseModel):
    id: UUID
    name: str


class PolicyTemplateCloneResponse(BaseModel):
    id: UUID
    organization_id: UUID
    template_id: UUID
    cloned_policy_id: UUID
    cloned_by: UUID
    cloned_at: datetime
    customization_notes: str | None = None
    template: PolicyTemplateSummary
    policy: PolicySummary


class PolicyTemplateStatsResponse(BaseModel):
    template_id: UUID
    template_name: str
    total_clones: int
    unique_orgs: int
    most_recent_clone_at: datetime | None = None


class TemplateCategoryCountResponse(BaseModel):
    category: str
    template_count: int


class TemplateFrameworkCountResponse(BaseModel):
    framework_tag: str
    template_count: int
