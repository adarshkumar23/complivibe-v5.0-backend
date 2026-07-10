import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SDFSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    suggested_sdf: bool
    sensitive_asset_count: int
    total_asset_count: int
    rationale: str
    provenance_json: dict
    confirmed: bool
    confirmed_value: bool | None
    confirmed_at: datetime | None
    created_at: datetime


class SDFConfirmRequest(BaseModel):
    confirmed_value: bool
    sdf_category: str | None = None


class SDFConfirmResult(BaseModel):
    organization_id: uuid.UUID
    is_significant_data_fiduciary: bool
    sdf_category: str | None
    obligation_state_ids: list[uuid.UUID]
    audit_schedule_id: uuid.UUID | None
