from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

CRITICALITY_TIERS = ("tier_1_critical", "tier_2_high", "tier_3_standard")
PROCESS_STATUSES = ("active", "archived")
FINANCIAL_IMPACT_TIERS = ("low", "medium", "high", "severe")


class BusinessProcessCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner_user_id: uuid.UUID | None = None
    criticality_tier: str = "tier_3_standard"
    recovery_time_objective_hours: int
    recovery_point_objective_hours: int
    dependencies_json: list[dict] | None = None
    status: str = "active"

    @field_validator("criticality_tier")
    @classmethod
    def _validate_criticality_tier(cls, value: str) -> str:
        if value not in CRITICALITY_TIERS:
            raise ValueError(f"criticality_tier must be one of {CRITICALITY_TIERS}")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in PROCESS_STATUSES:
            raise ValueError(f"status must be one of {PROCESS_STATUSES}")
        return value

    @field_validator("recovery_time_objective_hours", "recovery_point_objective_hours")
    @classmethod
    def _validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be a non-negative number of hours")
        return value

    @field_validator("dependencies_json")
    @classmethod
    def _validate_dependencies(cls, value: list[dict] | None) -> list[dict] | None:
        if value is None:
            return value
        for item in value:
            if "type" not in item or "name" not in item:
                raise ValueError("each dependency entry requires 'type' and 'name' keys")
            if item["type"] not in ("system", "vendor", "process"):
                raise ValueError("dependency 'type' must be one of 'system', 'vendor', 'process'")
        return value


class BusinessProcessUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    owner_user_id: uuid.UUID | None = None
    criticality_tier: str | None = None
    recovery_time_objective_hours: int | None = None
    recovery_point_objective_hours: int | None = None
    dependencies_json: list[dict] | None = None
    status: str | None = None

    @field_validator("criticality_tier")
    @classmethod
    def _validate_criticality_tier(cls, value: str | None) -> str | None:
        if value is not None and value not in CRITICALITY_TIERS:
            raise ValueError(f"criticality_tier must be one of {CRITICALITY_TIERS}")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in PROCESS_STATUSES:
            raise ValueError(f"status must be one of {PROCESS_STATUSES}")
        return value

    @field_validator("recovery_time_objective_hours", "recovery_point_objective_hours")
    @classmethod
    def _validate_non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("must be a non-negative number of hours")
        return value

    @field_validator("dependencies_json")
    @classmethod
    def _validate_dependencies(cls, value: list[dict] | None) -> list[dict] | None:
        if value is None:
            return value
        for item in value:
            if "type" not in item or "name" not in item:
                raise ValueError("each dependency entry requires 'type' and 'name' keys")
            if item["type"] not in ("system", "vendor", "process"):
                raise ValueError("dependency 'type' must be one of 'system', 'vendor', 'process'")
        return value


class BusinessProcessRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    owner_user_id: uuid.UUID | None
    criticality_tier: str
    recovery_time_objective_hours: int
    recovery_point_objective_hours: int
    dependencies_json: list[dict] | None
    status: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BiaAssessmentCreateRequest(BaseModel):
    impact_analysis_json: dict
    financial_impact_tier: str | None = None
    review_frequency_months: int = 12
    last_reviewed_at: datetime | None = Field(
        default=None,
        description=(
            "Only set this when recording a review that has genuinely already been "
            "completed (e.g. backfilling a historical review) -- it must be provided "
            "together with reviewed_by_user_id, never alone. Omit both to create a "
            "fresh, not-yet-reviewed BIA (last_reviewed_at will be null)."
        ),
    )
    reviewed_by_user_id: uuid.UUID | None = Field(
        default=None,
        description="Required together with last_reviewed_at -- the org member who performed the review being recorded.",
    )
    notes: str | None = None

    @field_validator("financial_impact_tier")
    @classmethod
    def _validate_financial_impact_tier(cls, value: str | None) -> str | None:
        if value is not None and value not in FINANCIAL_IMPACT_TIERS:
            raise ValueError(f"financial_impact_tier must be one of {FINANCIAL_IMPACT_TIERS}")
        return value

    @field_validator("review_frequency_months")
    @classmethod
    def _validate_review_frequency(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("review_frequency_months must be a positive number of months")
        return value

    @model_validator(mode="after")
    def _validate_review_pair(self) -> "BiaAssessmentCreateRequest":
        # last_reviewed_at asserts a review genuinely happened, so it must always be
        # accompanied by who performed it -- otherwise it's the same phantom
        # "reviewed by no one" state this item exists to fix (see G9 item 21).
        # reviewed_by_user_id may still be set alone (e.g. assigning ownership of a
        # not-yet-completed review) without implying a review timestamp.
        if self.last_reviewed_at is not None and self.reviewed_by_user_id is None:
            raise ValueError("reviewed_by_user_id is required when last_reviewed_at is provided")
        return self


class BiaAssessmentRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    process_id: uuid.UUID
    impact_analysis_json: dict
    financial_impact_tier: str | None
    review_frequency_months: int
    last_reviewed_at: datetime | None = None
    reviewed_by_user_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BiaAssessmentHistoryResponse(BaseModel):
    latest: BiaAssessmentRead | None
    history: list[BiaAssessmentRead]
    is_stale: bool = False
    context_flags: list[str] = Field(default_factory=list)


class OverdueReviewItem(BaseModel):
    process_id: uuid.UUID
    process_name: str
    criticality_tier: str
    latest_bia: BiaAssessmentRead | None
    is_stale: bool
    stale_reasons: list[str]


class OverdueReviewsResponse(BaseModel):
    items: list[OverdueReviewItem]
