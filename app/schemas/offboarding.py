from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OffboardingConfigurationRead(BaseModel):
    id: UUID
    organization_id: UUID
    default_successor_id: UUID | None = None
    require_successor_on_deactivate: bool
    created_at: datetime
    updated_at: datetime


class OffboardingConfigurationUpdate(BaseModel):
    default_successor_id: UUID | None = None
    require_successor_on_deactivate: bool | None = None


class OffboardingRunRequest(BaseModel):
    deactivated_user_id: UUID
    successor_id: UUID | None = None


class OffboardingValidationRead(BaseModel):
    risks_to_reassign: int
    controls_to_reassign: int
    tasks_to_reassign: int
    policies_to_reassign: int
    vendors_to_reassign: int
    audit_engagements_to_reassign: int
    total: int


class OffboardingRecordRead(BaseModel):
    id: UUID
    organization_id: UUID
    deactivated_user_id: UUID
    successor_id: UUID | None
    records_reassigned: dict
    total_reassigned: int
    executed_by: UUID
    executed_at: datetime
