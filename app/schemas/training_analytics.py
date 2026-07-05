from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrainingCompletionRecordCreate(BaseModel):
    user_id: UUID
    business_unit_id: UUID | None = None
    training_type: str = Field(min_length=1, max_length=100)
    assigned_at: datetime | None = None
    due_date: datetime
    score: int | None = Field(default=None, ge=0, le=100)


class TrainingCompletionRecordComplete(BaseModel):
    """Payload for PATCH /records/{id}: mark a training assignment completed."""

    completed_at: datetime | None = None
    score: int | None = Field(default=None, ge=0, le=100)


class TrainingCompletionRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    business_unit_id: UUID | None = None
    training_type: str
    assigned_at: datetime
    due_date: datetime
    completed_at: datetime | None = None
    score: int | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    is_overdue: bool = False


class OverdueTrainingDetail(BaseModel):
    record_id: UUID
    user_id: UUID
    training_type: str
    due_date: datetime


class BusinessUnitTrainingSummary(BaseModel):
    business_unit_id: UUID | None = None
    business_unit_name: str | None = None
    total_assigned: int
    completed_count: int
    completion_rate: float
    overdue_count: int
    overdue_rate: float
    trending_toward_noncompliance: bool
    overdue_details: list[OverdueTrainingDetail] = Field(default_factory=list)


class TrainingAnalyticsSummaryResponse(BaseModel):
    organization_id: UUID
    total_assigned: int
    total_completed: int
    overall_completion_rate: float
    overall_overdue_count: int
    overall_overdue_rate: float
    trending_threshold_note: str
    business_units: list[BusinessUnitTrainingSummary]
    generated_at: datetime
