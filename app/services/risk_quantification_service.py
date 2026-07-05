"""Quantitative risk assessment (Monte Carlo / FAIR) service.

Methodology reference:
    FAIR (Factor Analysis of Information Risk) taxonomy per The Open Group
    O-RT/O-RA standards, as restated by the FAIR Institute (fairinstitute.org)
    and Freund & Jones, "Measuring and Managing Information Risk: A FAIR
    Approach" (2015):

        Risk = Loss Event Frequency (LEF) x Loss Magnitude (LM)
        LEF  = Threat Event Frequency (TEF) x Vulnerability
        LM   = Primary Loss + Secondary Loss
        Secondary Loss = Secondary Loss Event Frequency (SLEF, a probability
                          0-1 conditioned on primary loss) x Secondary Loss
                          Magnitude (SLM)

    Input distributions follow FAIR practice: TEF and Vulnerability are
    modeled as PERT/Beta-PERT (min/most_likely/max, calibrated at ~90%
    confidence). Loss magnitudes (primary and secondary) are also modeled as
    PERT in this implementation for consistency of the input contract (a
    lognormal fit is offered as an alternative for the generic monte_carlo
    methodology below). Monte Carlo simulation uses N=10,000 iterations by
    default (the figure commonly cited in FAIR practice), aggregated into a
    Loss Exceedance Curve (x=annualized loss, y=P(loss>x)), reporting the
    Expected Annual Loss (mean of simulated annual loss) and a 90% confidence
    interval (5th/95th percentile of the simulated distribution).
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk import Risk
from app.models.risk_quantification import RiskQuantificationRun

_DEFAULT_N_ITERATIONS = 10000
_CURVE_POINTS = 20


def _require_numeric(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{field_name}' must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{field_name}' must be a number") from exc
    if not np.isfinite(result):
        raise ValueError(f"'{field_name}' must be a finite number")
    return result


def _validate_pert_triple(
    spec: Any, *, param_name: str, allow_max: float | None = None, min_floor: float = 0.0
) -> tuple[float, float, float]:
    """Validate and extract a {min, most_likely, max} PERT parameter triple."""
    if not isinstance(spec, dict):
        raise ValueError(f"'{param_name}' must be an object with 'min', 'most_likely', 'max' keys")

    missing = [key for key in ("min", "most_likely", "max") if key not in spec]
    if missing:
        raise ValueError(f"'{param_name}' is missing required keys: {', '.join(missing)}")

    lo = _require_numeric(spec["min"], f"{param_name}.min")
    mode = _require_numeric(spec["most_likely"], f"{param_name}.most_likely")
    hi = _require_numeric(spec["max"], f"{param_name}.max")

    if lo < min_floor:
        raise ValueError(f"'{param_name}.min' must be >= {min_floor}")
    if not (lo <= mode <= hi):
        raise ValueError(
            f"'{param_name}' must satisfy min <= most_likely <= max "
            f"(got min={lo}, most_likely={mode}, max={hi})"
        )
    if allow_max is not None and hi > allow_max:
        raise ValueError(f"'{param_name}.max' must be <= {allow_max}")

    return lo, mode, hi


def _sample_pert(lo: float, mode: float, hi: float, size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample from a Beta-PERT distribution via the standard PERT-to-Beta conversion.

    alpha = 1 + 4*(mode-min)/(max-min)
    beta  = 1 + 4*(max-mode)/(max-min)
    sample = min + Beta(alpha, beta) * (max-min)
    """
    if hi == lo:
        # Degenerate case: min == max (== mode, by validation) -> constant.
        return np.full(size, lo, dtype=float)

    alpha = 1.0 + 4.0 * (mode - lo) / (hi - lo)
    beta = 1.0 + 4.0 * (hi - mode) / (hi - lo)
    return lo + rng.beta(alpha, beta, size=size) * (hi - lo)


def _safe_correlation(sample: np.ndarray, target: np.ndarray) -> float:
    if np.std(sample) == 0 or np.std(target) == 0:
        return 0.0
    corr = np.corrcoef(sample, target)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(corr)


def _build_sensitivity(named_samples: dict[str, np.ndarray], annual_losses: np.ndarray) -> dict[str, Any]:
    ranking = [
        {"parameter": name, "correlation": _safe_correlation(sample, annual_losses)}
        for name, sample in named_samples.items()
    ]
    ranking.sort(key=lambda entry: abs(entry["correlation"]), reverse=True)
    most_influential = ranking[0]["parameter"] if ranking else None
    return {"most_influential_parameter": most_influential, "ranking": ranking}


def _build_loss_exceedance_curve(annual_losses: np.ndarray) -> list[dict[str, float]]:
    p99 = float(np.percentile(annual_losses, 99))
    upper = p99 if p99 > 0 else float(np.max(annual_losses)) or 1.0
    thresholds = np.linspace(0.0, upper, _CURVE_POINTS)
    curve = []
    for threshold in thresholds:
        probability = float(np.mean(annual_losses > threshold))
        curve.append({"loss_threshold": float(threshold), "probability_of_exceedance": probability})
    return curve


class RiskQuantificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get_risk_or_none(self, organization_id: uuid.UUID, risk_id: uuid.UUID) -> Risk | None:
        return self.db.execute(
            select(Risk).where(Risk.id == risk_id, Risk.organization_id == organization_id)
        ).scalar_one_or_none()

    def list_runs(self, organization_id: uuid.UUID, risk_id: uuid.UUID) -> list[RiskQuantificationRun]:
        return list(
            self.db.execute(
                select(RiskQuantificationRun)
                .where(
                    RiskQuantificationRun.organization_id == organization_id,
                    RiskQuantificationRun.risk_id == risk_id,
                )
                .order_by(RiskQuantificationRun.computed_at.desc())
            ).scalars()
        )

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def _simulate_fair(
        self, input_parameters: dict[str, Any], n_iterations: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        tef_lo, tef_mode, tef_hi = _validate_pert_triple(
            input_parameters.get("threat_event_frequency"), param_name="threat_event_frequency"
        )
        vuln_lo, vuln_mode, vuln_hi = _validate_pert_triple(
            input_parameters.get("vulnerability"), param_name="vulnerability", allow_max=1.0
        )
        pl_lo, pl_mode, pl_hi = _validate_pert_triple(
            input_parameters.get("primary_loss_magnitude"), param_name="primary_loss_magnitude"
        )

        secondary_spec = input_parameters.get("secondary_loss_event_frequency")
        magnitude_spec = input_parameters.get("secondary_loss_magnitude")
        has_secondary = secondary_spec is not None or magnitude_spec is not None
        if has_secondary:
            slef_lo, slef_mode, slef_hi = _validate_pert_triple(
                secondary_spec, param_name="secondary_loss_event_frequency", allow_max=1.0
            )
            slm_lo, slm_mode, slm_hi = _validate_pert_triple(
                magnitude_spec, param_name="secondary_loss_magnitude"
            )

        tef_sample = _sample_pert(tef_lo, tef_mode, tef_hi, n_iterations, rng)
        vulnerability_sample = _sample_pert(vuln_lo, vuln_mode, vuln_hi, n_iterations, rng)
        primary_loss_sample = _sample_pert(pl_lo, pl_mode, pl_hi, n_iterations, rng)

        if has_secondary:
            slef_sample = _sample_pert(slef_lo, slef_mode, slef_hi, n_iterations, rng)
            slm_sample = _sample_pert(slm_lo, slm_mode, slm_hi, n_iterations, rng)
            secondary_loss = slef_sample * slm_sample
        else:
            slef_sample = np.zeros(n_iterations, dtype=float)
            slm_sample = np.zeros(n_iterations, dtype=float)
            secondary_loss = np.zeros(n_iterations, dtype=float)

        lef = tef_sample * vulnerability_sample
        loss_magnitude = primary_loss_sample + secondary_loss
        annual_losses = lef * loss_magnitude

        named_samples = {
            "threat_event_frequency": tef_sample,
            "vulnerability": vulnerability_sample,
            "primary_loss_magnitude": primary_loss_sample,
        }
        if has_secondary:
            named_samples["secondary_loss_event_frequency"] = slef_sample
            named_samples["secondary_loss_magnitude"] = slm_sample

        return annual_losses, named_samples

    def _simulate_monte_carlo(
        self, input_parameters: dict[str, Any], n_iterations: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        frequency_spec = input_parameters.get("frequency")
        loss_spec = input_parameters.get("loss_magnitude")
        if not isinstance(frequency_spec, dict):
            raise ValueError("'frequency' must be an object describing the frequency distribution")
        if not isinstance(loss_spec, dict):
            raise ValueError("'loss_magnitude' must be an object describing the loss magnitude distribution")

        freq_distribution = frequency_spec.get("distribution")
        if freq_distribution == "poisson":
            lam = frequency_spec.get("lam")
            if lam is None:
                raise ValueError("'frequency.lam' is required for a poisson distribution")
            lam = _require_numeric(lam, "frequency.lam")
            if lam <= 0:
                raise ValueError("'frequency.lam' must be > 0")
            frequency_sample = rng.poisson(lam=lam, size=n_iterations).astype(float)
        elif freq_distribution == "pert":
            f_lo, f_mode, f_hi = _validate_pert_triple(frequency_spec, param_name="frequency")
            frequency_sample = _sample_pert(f_lo, f_mode, f_hi, n_iterations, rng)
        else:
            raise ValueError("'frequency.distribution' must be 'poisson' or 'pert'")

        loss_distribution = loss_spec.get("distribution")
        if loss_distribution == "lognormal":
            mean = loss_spec.get("mean")
            sigma = loss_spec.get("sigma")
            if mean is None or sigma is None:
                raise ValueError("'loss_magnitude.mean' and 'loss_magnitude.sigma' are required for a lognormal distribution")
            mean = _require_numeric(mean, "loss_magnitude.mean")
            sigma = _require_numeric(sigma, "loss_magnitude.sigma")
            if mean <= 0:
                raise ValueError("'loss_magnitude.mean' must be > 0")
            if sigma <= 0:
                raise ValueError("'loss_magnitude.sigma' must be > 0")
            # mean/sigma here parameterize the underlying normal distribution
            # in log-space, matching numpy.random.lognormal's (mean, sigma) API.
            loss_magnitude_sample = rng.lognormal(mean=mean, sigma=sigma, size=n_iterations)
        elif loss_distribution == "pert":
            l_lo, l_mode, l_hi = _validate_pert_triple(loss_spec, param_name="loss_magnitude")
            loss_magnitude_sample = _sample_pert(l_lo, l_mode, l_hi, n_iterations, rng)
        else:
            raise ValueError("'loss_magnitude.distribution' must be 'lognormal' or 'pert'")

        annual_losses = frequency_sample * loss_magnitude_sample
        named_samples = {
            "frequency": frequency_sample,
            "loss_magnitude": loss_magnitude_sample,
        }
        return annual_losses, named_samples

    def compute_quantification(
        self,
        *,
        risk: Risk,
        methodology: str,
        input_parameters: dict[str, Any],
        n_iterations: int = _DEFAULT_N_ITERATIONS,
        computed_by_user_id: uuid.UUID | None = None,
    ) -> RiskQuantificationRun:
        if methodology not in ("monte_carlo", "fair"):
            raise ValueError("'methodology' must be 'monte_carlo' or 'fair'")
        if not isinstance(input_parameters, dict) or not input_parameters:
            raise ValueError("'input_parameters' must be a non-empty object")
        if n_iterations < 1000:
            raise ValueError("'n_iterations' must be >= 1000 for a statistically meaningful simulation")

        rng = np.random.default_rng()

        if methodology == "fair":
            annual_losses, named_samples = self._simulate_fair(input_parameters, n_iterations, rng)
        else:
            annual_losses, named_samples = self._simulate_monte_carlo(input_parameters, n_iterations, rng)

        if not np.all(np.isfinite(annual_losses)):
            raise ValueError("Simulation produced non-finite loss values; check input parameters")
        if not np.all(annual_losses >= 0):
            raise RuntimeError(
                "Internal error: Monte Carlo simulation produced a negative annualized loss sample; "
                "this indicates a bug in the sampling logic, not a data problem."
            )

        expected_annual_loss = float(np.mean(annual_losses))
        confidence_intervals = {
            "p05": float(np.percentile(annual_losses, 5)),
            "p50": float(np.percentile(annual_losses, 50)),
            "p95": float(np.percentile(annual_losses, 95)),
        }
        loss_exceedance_curve = _build_loss_exceedance_curve(annual_losses)
        sensitivity = _build_sensitivity(named_samples, annual_losses)

        run = RiskQuantificationRun(
            organization_id=risk.organization_id,
            risk_id=risk.id,
            methodology=methodology,
            input_parameters_json=input_parameters,
            loss_exceedance_curve_json=loss_exceedance_curve,
            expected_annual_loss=expected_annual_loss,
            confidence_intervals_json=confidence_intervals,
            sensitivity_json=sensitivity,
            computed_by_user_id=computed_by_user_id,
        )
        self.db.add(run)
        self.db.flush()
        return run
