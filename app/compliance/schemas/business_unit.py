import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BusinessUnitCreate(BaseModel):
    name: str
    code: str
    parent_bu_id: uuid.UUID | None = None
    description: str | None = None
    cost_center: str | None = None
    bu_lead_user_id: uuid.UUID | None = None


class BusinessUnitUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    parent_bu_id: uuid.UUID | None = None
    description: str | None = None
    cost_center: str | None = None
    bu_lead_user_id: uuid.UUID | None = None
    is_active: bool | None = None


class BusinessUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    parent_bu_id: uuid.UUID | None
    description: str | None
    cost_center: str | None
    bu_lead_user_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    active_child_count: int = 0
    total_child_count: int = 0
    tagged_entity_count: int = 0
    context_flags: list[str] = []


class EntityTagRequest(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    business_unit_id: uuid.UUID | None = None
