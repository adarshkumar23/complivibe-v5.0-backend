from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RiskQuantificationRequest(BaseModel):
    methodology: str = Field(pattern="^(monte_carlo|fair|fair_bayesian)$")
    input_parameters: dict[str, Any]
    n_iterations: int = Field(default=10000, ge=1000, le=200000)


class RiskQuantificationLossExceedancePoint(BaseModel):
    loss_threshold: float
    probability_of_exceedance: float


class RiskQuantificationSensitivityRankingEntry(BaseModel):
    parameter: str
    correlation: float


class RiskQuantificationSensitivity(BaseModel):
    most_influential_parameter: str
    ranking: list[RiskQuantificationSensitivityRankingEntry]


class RiskQuantificationConfidenceIntervals(BaseModel):
    p05: float
    p50: float
    p95: float


class RiskQuantificationRunRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    risk_id: uuid.UUID
    methodology: str
    input_parameters_json: dict[str, Any]
    loss_exceedance_curve_json: list[RiskQuantificationLossExceedancePoint]
    expected_annual_loss: float
    confidence_intervals_json: RiskQuantificationConfidenceIntervals
    sensitivity_json: RiskQuantificationSensitivity
    computed_at: datetime
    computed_by_user_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}
