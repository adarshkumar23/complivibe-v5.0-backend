from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

IP_ASSET_TYPES = ("patent", "trademark", "model_license", "dataset_license")
IP_ASSET_TYPE_PATTERN = "^(" + "|".join(IP_ASSET_TYPES) + ")$"

IP_ASSET_STATUSES = ("active", "expired", "terminated", "pending_renewal")
IP_ASSET_STATUS_PATTERN = "^(" + "|".join(IP_ASSET_STATUSES) + ")$"


class IPAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(pattern=IP_ASSET_TYPE_PATTERN)
    licensor: str | None = Field(default=None, max_length=255)
    licensee: str | None = Field(default=None, max_length=255)
    terms: dict | None = None
    expiry_date: datetime | None = None
    linked_ai_system_id: UUID | None = None
    status: str = Field(default="active", pattern=IP_ASSET_STATUS_PATTERN)


class IPAssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: str | None = Field(default=None, pattern=IP_ASSET_TYPE_PATTERN)
    licensor: str | None = Field(default=None, max_length=255)
    licensee: str | None = Field(default=None, max_length=255)
    terms: dict | None = None
    expiry_date: datetime | None = None
    linked_ai_system_id: UUID | None = None
    status: str | None = Field(default=None, pattern=IP_ASSET_STATUS_PATTERN)


class IPAssetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    asset_type: str
    licensor: str | None = None
    licensee: str | None = None
    terms: dict | None = None
    expiry_date: datetime | None = None
    linked_ai_system_id: UUID | None = None
    status: str
    created_by: UUID | None = None
    is_expiring_soon: bool = False
    is_expired: bool = False
    days_until_expiry: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AtRiskAISystem(BaseModel):
    id: UUID
    name: str
    lifecycle_status: str
    still_active: bool


class ExpiringIPAssetResponse(IPAssetResponse):
    at_risk_ai_system: AtRiskAISystem | None = None


class IPAssetSettingsResponse(BaseModel):
    id: UUID
    organization_id: UUID
    expiring_soon_window_days: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IPAssetSettingsUpdate(BaseModel):
    expiring_soon_window_days: int = Field(gt=0, le=3650)
