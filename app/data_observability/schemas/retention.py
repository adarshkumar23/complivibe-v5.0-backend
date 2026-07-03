import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DataRetentionPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    retention_days: int = Field(ge=1)
    max_retention_days: int | None = Field(default=None, ge=1)
    applies_to_classification_types: list[str] = Field(default_factory=list)
    applies_to_sensitivity_tiers: list[str] = Field(default_factory=list)
    legal_basis: str | None = None
    action_on_expiry: str = "flag"
    legal_hold: bool = False


class DataRetentionPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    retention_days: int | None = Field(default=None, ge=1)
    max_retention_days: int | None = Field(default=None, ge=1)
    applies_to_classification_types: list[str] | None = None
    applies_to_sensitivity_tiers: list[str] | None = None
    legal_basis: str | None = None
    action_on_expiry: str | None = None
    legal_hold: bool | None = None
    is_active: bool | None = None


class DataRetentionPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    retention_days: int
    max_retention_days: int | None
    applies_to_classification_types: list
    applies_to_sensitivity_tiers: list
    legal_basis: str | None
    action_on_expiry: str
    legal_hold: bool
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ApplyPolicyRequest(BaseModel):
    data_asset_id: uuid.UUID


class DataRetentionReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    data_asset_id: uuid.UUID
    policy_id: uuid.UUID | None
    status: str
    review_type: str
    days_overdue: int | None
    required_action: str
    linked_task_id: uuid.UUID | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    evidence_notes: str | None
    created_at: datetime
    updated_at: datetime


class ResolveReviewRequest(BaseModel):
    evidence_notes: str | None = None


class WaiveReviewRequest(BaseModel):
    reason: str = Field(min_length=1)


class RetentionSummaryRead(BaseModel):
    total_assets_with_policy: int
    expired_count: int
    pending_reviews: int
    by_required_action: dict[str, int]
    compliance_rate: float


class RetentionSweepRead(BaseModel):
    assets_flagged: int
    tasks_created: int
    reminders_queued: int


class RetentionLegalHoldUpdateRequest(BaseModel):
    legal_hold: bool
