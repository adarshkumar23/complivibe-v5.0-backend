import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AISystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    system_type: str
    owner_id: uuid.UUID
    description: str | None = None
    vendor_id: uuid.UUID | None = None
    deployment_status: str = "development"
    risk_tier: str | None = None
    data_sources_description: str | None = None
    purpose: str | None = None
    affected_population: str | None = None
    geographic_scope: list[str] | None = None
    model_version: str | None = Field(default=None, max_length=128)


class AISystemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    system_type: str | None = None
    owner_id: uuid.UUID | None = None
    description: str | None = None
    vendor_id: uuid.UUID | None = None
    deployment_status: str | None = None
    risk_tier: str | None = None
    data_sources_description: str | None = None
    purpose: str | None = None
    affected_population: str | None = None
    geographic_scope: list[str] | None = None
    model_version: str | None = Field(default=None, max_length=128)


class AISystemStatusUpdate(BaseModel):
    new_status: str


class AISystemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    system_type: str
    owner_id: uuid.UUID | None
    description: str | None
    vendor_id: uuid.UUID | None
    deployment_status: str
    risk_tier: str | None
    data_sources_description: str | None
    purpose: str | None
    affected_population: str | None
    geographic_scope: Any | None
    model_version: str | None = None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class AISystemSummaryRead(BaseModel):
    total: int
    by_system_type: dict[str, int]
    by_deployment_status: dict[str, int]
    by_risk_tier: dict[str, int]
    unclassified_count: int


class AIUseCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    business_owner_id: uuid.UUID
    use_case_type: str
    description: str | None = None
    is_high_stakes: bool = False
    affected_groups: str | None = None
    deployment_context: str | None = None


class AIUseCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    business_owner_id: uuid.UUID | None = None
    use_case_type: str | None = None
    description: str | None = None
    is_high_stakes: bool | None = None
    affected_groups: str | None = None
    deployment_context: str | None = None


class AIUseCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    name: str
    description: str | None
    business_owner_id: uuid.UUID
    use_case_type: str
    is_high_stakes: bool
    affected_groups: str | None
    deployment_context: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
