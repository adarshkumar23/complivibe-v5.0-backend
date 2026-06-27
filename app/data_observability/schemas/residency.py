import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DataResidencyPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    required_countries: list[str] = Field(default_factory=list)
    prohibited_countries: list[str] = Field(default_factory=list)
    require_eea_only: bool = False
    require_domestic_only: bool = False
    legal_basis: str | None = None
    applies_to_classification_types: list[str] = Field(default_factory=list)
    applies_to_sensitivity_tiers: list[str] = Field(default_factory=list)


class DataResidencyPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    required_countries: list[str] | None = None
    prohibited_countries: list[str] | None = None
    require_eea_only: bool | None = None
    require_domestic_only: bool | None = None
    legal_basis: str | None = None
    applies_to_classification_types: list[str] | None = None
    applies_to_sensitivity_tiers: list[str] | None = None
    is_active: bool | None = None


class DataResidencyPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    required_countries: list
    prohibited_countries: list
    require_eea_only: bool
    require_domestic_only: bool
    legal_basis: str | None
    applies_to_classification_types: list
    applies_to_sensitivity_tiers: list
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class DataResidencyViolationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    data_asset_id: uuid.UUID
    policy_id: uuid.UUID
    violation_type: str
    detected_at: datetime
    violating_locations: list
    status: str
    acknowledged_by: uuid.UUID | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    linked_incident_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DataResidencyCheckRead(BaseModel):
    asset_id: str
    asset_name: str
    compliant: bool
    policy_results: list[dict]


class DataResidencySweepRead(BaseModel):
    assets_checked: int
    violations_found: int
    incidents_created: int


class DataResidencySummaryRead(BaseModel):
    total_assets_checked: int
    compliant_count: int
    violation_count: int
    open_violations: int
    by_violation_type: dict[str, int]
    assets_with_open_violations: list[dict]
    eea_compliant_pct: float
