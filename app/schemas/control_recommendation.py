from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

CONTROL_RECOMMENDATION_CAVEAT = (
    "This recommendation is generated deterministically from CompliVibe records and configured framework content. "
    "It is not legal advice or a final compliance determination."
)


class ControlRecommendationRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID
    obligation_id: UUID
    suggestion_id: UUID | None = None
    recommendation_type: str
    priority: str
    status: str
    title: str
    rationale: str
    recommended_control_title: str | None = None
    recommended_control_description: str | None = None
    existing_control_id: UUID | None = None
    created_control_id: UUID | None = None
    confidence_level: str
    source: str
    provenance_json: dict | None = None
    generated_by_user_id: UUID | None = None
    generated_at: datetime
    applied_by_user_id: UUID | None = None
    applied_at: datetime | None = None
    dismissed_by_user_id: UUID | None = None
    dismissed_at: datetime | None = None
    dismissal_reason: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ControlRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    include_non_applicable_review: bool = False
    limit: int = Field(default=100, ge=1, le=500)


class ControlRecommendationGenerateResponse(BaseModel):
    run_id: UUID | None = None
    dry_run: bool
    recommendations: list[ControlRecommendationRead]
    summary: dict
    caveat: str = CONTROL_RECOMMENDATION_CAVEAT


class ControlRecommendationApplyRequest(BaseModel):
    existing_control_id: UUID | None = None
    create_control: bool = True
    notes: str | None = None


class ControlRecommendationDismissRequest(BaseModel):
    dismissal_reason: str = Field(min_length=1)


class RecommendationGenerationRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    framework_id: UUID | None = None
    dry_run: bool
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    evaluated_obligations_count: int
    recommendations_created_count: int
    recommendations_skipped_duplicate_count: int
    recommendations_would_create_count: int
    summary_json: dict | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ControlRecommendationSummary(BaseModel):
    open_recommendations: int
    applied_recommendations: int
    dismissed_recommendations: int
    critical_recommendations: int
    high_recommendations: int
    create_control_recommendations: int
    evidence_recommendations: int
    applicability_review_recommendations: int
    recommendations_generated_last_30d: int
