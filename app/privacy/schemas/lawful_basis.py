import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LawfulBasisCreate(BaseModel):
    processing_activity_id: uuid.UUID
    lawful_basis: str
    basis_description: str = Field(min_length=1)
    applicable_frameworks: list[str] = Field(default_factory=list)
    article_reference: str | None = Field(default=None, max_length=255)
    legitimate_interest_assessment: str | None = None
    review_required_at: date | None = None


class LawfulBasisUpdate(BaseModel):
    basis_description: str | None = None
    applicable_frameworks: list[str] | None = None
    article_reference: str | None = Field(default=None, max_length=255)
    legitimate_interest_assessment: str | None = None
    review_required_at: date | None = None
    is_active: bool | None = None


class LawfulBasisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    processing_activity_id: uuid.UUID
    lawful_basis: str
    basis_description: str
    applicable_frameworks: list
    article_reference: str | None
    legitimate_interest_assessment: str | None
    review_required_at: date | None
    is_active: bool
    documented_by: uuid.UUID
    documented_at: datetime
    created_at: datetime
    updated_at: datetime


class LawfulBasisSummaryRead(BaseModel):
    total_activities_with_basis: int
    activities_without_basis: int
    by_lawful_basis: dict[str, int]
    legitimate_interests_count: int
    review_due_count: int
