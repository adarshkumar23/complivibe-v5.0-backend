import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DataAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: str
    description: str | None = None
    owner_id: uuid.UUID
    custodian_id: uuid.UUID | None = None
    sensitivity_tier: str | None = None
    classification_type: str | None = None
    classification_confidence: Decimal | None = None
    classification_source: str | None = None
    classification_confirmed: bool = False
    geographic_locations: list[str] = Field(default_factory=list)
    permitted_regions: list[str] = Field(default_factory=list)
    schema_column_names: list[str] | None = None
    retention_policy_days: int | None = None
    retention_review_date: date | None = None
    data_volume_estimate: str | None = Field(default=None, max_length=100)
    source_system: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)
    is_phi: bool = False
    hipaa_safeguard_required: str | None = Field(default=None, max_length=20)
    status: str = "active"


class DataAssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: str | None = None
    description: str | None = None
    owner_id: uuid.UUID | None = None
    custodian_id: uuid.UUID | None = None
    sensitivity_tier: str | None = None
    classification_type: str | None = None
    classification_confidence: Decimal | None = None
    classification_source: str | None = None
    classification_confirmed: bool | None = None
    geographic_locations: list[str] | None = None
    permitted_regions: list[str] | None = None
    schema_column_names: list[str] | None = None
    retention_policy_days: int | None = None
    retention_review_date: date | None = None
    data_volume_estimate: str | None = Field(default=None, max_length=100)
    source_system: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    is_phi: bool | None = None
    hipaa_safeguard_required: str | None = Field(default=None, max_length=20)
    status: str | None = None


class DataAssetConfirmClassificationRequest(BaseModel):
    classification_type: str
    sensitivity_tier: str


class DataAssetClassifySampleRequest(BaseModel):
    sample_text: str = Field(min_length=1)
    language: str = Field(default="en", min_length=2, max_length=10)


class DataAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    asset_type: str
    description: str | None
    owner_id: uuid.UUID
    custodian_id: uuid.UUID | None
    sensitivity_tier: str | None
    classification_type: str | None
    classification_confidence: Decimal | None
    classification_source: str | None
    classification_confirmed: bool
    geographic_locations: list
    permitted_regions: list
    schema_column_names: list | None
    retention_policy_days: int | None
    retention_review_date: date | None
    data_volume_estimate: str | None
    source_system: str | None
    tags: list
    is_phi: bool
    hipaa_safeguard_required: str | None
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    classification_age_days: int | None = None
    classification_stale: bool = False
    recommended_review: str | None = None
    context_flags: list[str] = []


class DataAssetSummaryRead(BaseModel):
    total_assets: int
    by_asset_type: dict[str, int]
    by_sensitivity_tier: dict[str, int]
    by_classification_type: dict[str, int]
    confirmed_count: int
    unconfirmed_count: int
    needs_review_count: int
    stale_classification_count: int
    high_risk_unconfirmed_count: int


class PresidioEntity(BaseModel):
    entity_type: str
    score: float
    start: int
    end: int


class DataAssetSampleClassificationRead(BaseModel):
    status: str
    message: str | None = None
    entities: list[PresidioEntity] | list[dict]
    suggested_classification: str | None = None
    suggested_sensitivity_tier: str | None = None
    confidence: float | None = None
    source: str | None = None
    warning: str | None = None
