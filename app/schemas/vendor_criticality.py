from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

DATA_VOLUME_TIER_PATTERN = "^(none|low|medium|high|very_high)$"
OPERATIONAL_CRITICALITY_PATTERN = "^(low|medium|high|critical)$"
CRITICALITY_TIER_PATTERN = "^(low|medium|high|critical)$"


class VendorCriticalityWeightsMixin(BaseModel):
    revenue_dependency_weight: Decimal = Field(default=Decimal("0.2500"), ge=0, le=1, max_digits=6, decimal_places=4)
    data_volume_weight: Decimal = Field(default=Decimal("0.2500"), ge=0, le=1, max_digits=6, decimal_places=4)
    operational_criticality_weight: Decimal = Field(default=Decimal("0.2500"), ge=0, le=1, max_digits=6, decimal_places=4)
    substitutability_weight: Decimal = Field(default=Decimal("0.2500"), ge=0, le=1, max_digits=6, decimal_places=4)

    @model_validator(mode="after")
    def validate_positive_weight_total(self):
        total = (
            self.revenue_dependency_weight
            + self.data_volume_weight
            + self.operational_criticality_weight
            + self.substitutability_weight
        )
        if total <= 0:
            raise ValueError("At least one criticality weight must be greater than zero")
        return self


class VendorCriticalitySettingUpdate(VendorCriticalityWeightsMixin):
    pass


class VendorCriticalitySettingRead(VendorCriticalityWeightsMixin):
    id: UUID | None = None
    organization_id: UUID
    updated_by_user_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_default: bool = False


class VendorCriticalityProfileUpdate(BaseModel):
    revenue_dependency_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=5, decimal_places=2)
    data_volume_tier: str = Field(default="none", pattern=DATA_VOLUME_TIER_PATTERN)
    operational_criticality: str = Field(default="low", pattern=OPERATIONAL_CRITICALITY_PATTERN)
    substitutability_score: int = Field(default=1, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=2000)


class VendorCriticalityProfileRead(BaseModel):
    id: UUID | None = None
    organization_id: UUID
    vendor_id: UUID
    revenue_dependency_pct: Decimal
    data_volume_tier: str
    operational_criticality: str
    substitutability_score: int
    criticality_score: int
    criticality_tier: str = Field(pattern=CRITICALITY_TIER_PATTERN)
    score_explanation_json: dict | list
    priority_context: dict = Field(default_factory=dict)
    notes: str | None = None
    updated_by_user_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_default: bool = False
    profile_age_days: float | None = None
    is_stale: bool = False
    stale_after_days: int = 180
    context_flags: list[str] = Field(default_factory=list)


class VendorCriticalityPreview(BaseModel):
    revenue_dependency_pct: Decimal
    data_volume_tier: str
    operational_criticality: str
    substitutability_score: int
    criticality_score: int
    criticality_tier: str
    score_explanation_json: dict | list
    computed_at: datetime
