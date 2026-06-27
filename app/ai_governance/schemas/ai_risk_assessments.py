import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AIRiskAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    assessment_version: int
    status: str
    bias_risk_rating: str | None
    fairness_risk_rating: str | None
    explainability_risk_rating: str | None
    privacy_risk_rating: str | None
    misuse_risk_rating: str | None
    security_risk_rating: str | None
    overall_risk_score: Decimal | None
    assessment_bias_results: dict[str, Any] | None
    completed_by: uuid.UUID | None
    completed_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AIRiskAssessmentResponseSubmitItem(BaseModel):
    question_id: uuid.UUID
    response: str = Field(pattern="^(low_risk|medium_risk|high_risk|critical_risk)$")
    notes: str | None = None


class AIRiskAssessmentResponseSubmitRequest(BaseModel):
    responses: list[AIRiskAssessmentResponseSubmitItem]


class ComputeBiasRequest(BaseModel):
    predictions: list[int | float]
    protected_attribute_values: list[int | float]
    labels: list[int | float] | None = None
