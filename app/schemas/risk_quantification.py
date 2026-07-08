from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Kept in sync with RiskQuantificationService's own cap: PyMC prior-predictive sampling
# for methodology="fair_bayesian" runs synchronously within the request/response cycle,
# so n_iterations is capped lower than the plain-numpy "fair"/"monte_carlo" methodologies.
from app.services.risk_quantification_service import MAX_BAYESIAN_N_ITERATIONS


class PertTriple(BaseModel):
    """A {min, most_likely, max} PERT/Beta-PERT parameter triple, per FAIR practice
    (calibrated expert-judgment min/most-likely/max estimates, ~90% confidence)."""

    model_config = ConfigDict(extra="forbid")

    min: float = Field(ge=0.0, description="Lower-bound estimate")
    most_likely: float = Field(ge=0.0, description="Modal (most likely) estimate")
    max: float = Field(ge=0.0, description="Upper-bound estimate")

    @model_validator(mode="after")
    def _validate_order(self) -> "PertTriple":
        if not (self.min <= self.most_likely <= self.max):
            raise ValueError(
                "must satisfy min <= most_likely <= max "
                f"(got min={self.min}, most_likely={self.most_likely}, max={self.max})"
            )
        return self


class ProbabilityPertTriple(PertTriple):
    """A PERT triple additionally constrained to the [0, 1] probability range -- used
    for FAIR inputs that are themselves probabilities (vulnerability,
    secondary_loss_event_frequency)."""

    min: float = Field(ge=0.0, le=1.0)
    most_likely: float = Field(ge=0.0, le=1.0)
    max: float = Field(ge=0.0, le=1.0)


class PoissonFrequency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution: Literal["poisson"]
    lam: float = Field(gt=0, description="Poisson rate parameter: expected number of loss events per year")


class PertFrequency(PertTriple):
    model_config = ConfigDict(extra="forbid")

    distribution: Literal["pert"]


FrequencyDistribution = Annotated[Union[PoissonFrequency, PertFrequency], Field(discriminator="distribution")]


class LognormalLossMagnitude(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution: Literal["lognormal"]
    mean: float = Field(gt=0, description="Mean of the underlying normal distribution, in log-space")
    sigma: float = Field(gt=0, description="Standard deviation of the underlying normal distribution, in log-space")


class PertLossMagnitude(PertTriple):
    model_config = ConfigDict(extra="forbid")

    distribution: Literal["pert"]


LossMagnitudeDistribution = Annotated[
    Union[LognormalLossMagnitude, PertLossMagnitude], Field(discriminator="distribution")
]


class MonteCarloInputParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frequency: FrequencyDistribution
    loss_magnitude: LossMagnitudeDistribution


class FairInputParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threat_event_frequency: PertTriple
    vulnerability: ProbabilityPertTriple
    primary_loss_magnitude: PertTriple
    secondary_loss_event_frequency: ProbabilityPertTriple | None = None
    secondary_loss_magnitude: PertTriple | None = None

    @model_validator(mode="after")
    def _secondary_both_or_neither(self) -> "FairInputParameters":
        has_frequency = self.secondary_loss_event_frequency is not None
        has_magnitude = self.secondary_loss_magnitude is not None
        if has_frequency != has_magnitude:
            raise ValueError(
                "secondary_loss_event_frequency and secondary_loss_magnitude must both be "
                "provided together, or neither (partial secondary-loss modeling is not supported)"
            )
        return self


class MonteCarloQuantificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    methodology: Literal["monte_carlo"]
    input_parameters: MonteCarloInputParameters
    n_iterations: int = Field(default=10000, ge=1000, le=200000)


class FairQuantificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    methodology: Literal["fair"]
    input_parameters: FairInputParameters
    n_iterations: int = Field(default=10000, ge=1000, le=200000)


class FairBayesianQuantificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    methodology: Literal["fair_bayesian"]
    input_parameters: FairInputParameters
    n_iterations: int = Field(
        default=10000,
        ge=1000,
        le=MAX_BAYESIAN_N_ITERATIONS,
        description=(
            "Capped lower than 'fair'/'monte_carlo' -- PyMC prior-predictive sampling for "
            "this methodology runs synchronously within the request."
        ),
    )


RiskQuantificationRequest = Annotated[
    Union[MonteCarloQuantificationRequest, FairQuantificationRequest, FairBayesianQuantificationRequest],
    Field(discriminator="methodology"),
]


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


class RiskQuantificationAppetiteComparison(BaseModel):
    risk_category: str
    max_acceptable_score: int
    current_risk_score: int | None = None
    breached: bool
    escalation_owner_id: uuid.UUID


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
    context_flags: list[str] = Field(default_factory=list)
    percent_change_from_previous_run: float | None = None
    appetite_comparison: RiskQuantificationAppetiteComparison | None = None

    model_config = {"from_attributes": True}
