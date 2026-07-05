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
import scipy.stats as stats
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk import Risk
from app.models.risk_quantification import RiskQuantificationRun

_DEFAULT_N_ITERATIONS = 10000
_CURVE_POINTS = 20

# PyMC prior-predictive sampling (methodology="fair_bayesian") runs synchronously
# within the request/response cycle -- there is no background task/worker
# infrastructure in app/workers/ yet (it is currently an empty package) to
# offload this to. 20,000 draws over a 3-5 variable model completes in ~2s on
# commodity hardware (hand-timed during development); this cap keeps the
# worst case comfortably under 10s so the endpoint never hangs. Callers that
# need more draws should use methodology="fair" (pure numpy Monte Carlo, no
# PyMC/compilation overhead), which already supports up to 200,000 iterations.
_MAX_BAYESIAN_N_ITERATIONS = 20000


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


def _pert_to_beta_shape(lo: float, mode: float, hi: float) -> tuple[float, float]:
    """Analytically derive the Beta-PERT shape parameters (alpha, beta) for a
    {min, most_likely, max} triple, using the standard PERT-to-Beta conversion:

        alpha = 1 + 4*(mode-min)/(max-min)
        beta  = 1 + 4*(max-mode)/(max-min)

    These parameterize a scipy.stats.beta distribution on [0, 1] which is then
    affinely rescaled to [lo, hi]. This is the same conversion used by
    `_sample_pert` above (kept in sync deliberately, so the Bayesian prior and
    the plain Monte Carlo sampler encode the identical FAIR-standard PERT
    calibration) but expressed as explicit distribution *parameters* rather
    than a direct sample, since PyMC priors need shape parameters and we use
    scipy.stats.beta here (rather than hand-deriving moments) to validate them.
    """
    if hi == lo:
        # Degenerate (constant) case: caller must special-case this before
        # constructing a PyMC Beta prior, since alpha/beta are undefined.
        raise ValueError("PERT shape parameters are undefined when min == max")

    alpha = 1.0 + 4.0 * (mode - lo) / (hi - lo)
    beta = 1.0 + 4.0 * (hi - mode) / (hi - lo)

    # Sanity-check the derived shape parameters against scipy.stats.beta's
    # analytic mean in unit space: for a well-formed PERT triple the Beta
    # mean should sit between 0 and 1 and roughly track (mode-lo)/(hi-lo).
    unit_mean = stats.beta(alpha, beta).mean()
    if not np.isfinite(unit_mean) or not (0.0 <= unit_mean <= 1.0):
        raise ValueError(
            "Derived Beta-PERT shape parameters are invalid for the given "
            "min/most_likely/max triple"
        )
    return alpha, beta


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

    def _simulate_fair_bayesian(
        self, input_parameters: dict[str, Any], n_iterations: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Real Bayesian FAIR model via PyMC prior-predictive sampling.

        TEF, Vulnerability, Primary Loss (and, if provided, Secondary Loss
        Event Frequency / Magnitude) are each modeled as genuine PyMC random
        variables: a pm.Beta on [0, 1] whose shape parameters are derived
        analytically from the input min/most_likely/max triple via the same
        Beta-PERT conversion as the rest of this module (see
        `_pert_to_beta_shape`), affinely rescaled with a pm.Deterministic to
        the variable's actual [min, max] range.

        There is no observed data here -- FAIR is a generative expert-judgment
        risk model, not something fit to a data sample -- so the correct
        Bayesian operation is prior predictive simulation
        (`pm.sample_prior_predictive`), which forward-samples the full joint
        model (TEF, Vulnerability, Primary Loss, Secondary Loss, and their
        deterministic combination into annualized loss) while properly
        propagating each variable's uncertainty through the LEF x Loss Magnitude
        FAIR relationship. Full posterior MCMC (`pm.sample`) is deliberately
        NOT used: there's no likelihood to condition on, and NUTS sampling of
        this model is measurably slower for no benefit (hand-timed at several
        seconds longer for equivalent draw counts with no observed-data
        constraint to justify it).
        """
        import pymc as pm

        if n_iterations > _MAX_BAYESIAN_N_ITERATIONS:
            raise ValueError(
                f"'n_iterations' must be <= {_MAX_BAYESIAN_N_ITERATIONS} for the "
                "'fair_bayesian' methodology (PyMC prior-predictive sampling runs "
                "synchronously within the request; use methodology='fair' for "
                "higher iteration counts)"
            )

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

        seed = int(rng.integers(0, 2**31 - 1))

        with pm.Model():
            tef_variables = []
            if tef_hi == tef_lo:
                tef = pm.Deterministic("threat_event_frequency", pm.math.constant(tef_lo))
            else:
                a, b = _pert_to_beta_shape(tef_lo, tef_mode, tef_hi)
                tef_raw = pm.Beta("tef_raw", alpha=a, beta=b)
                tef = pm.Deterministic("threat_event_frequency", tef_lo + tef_raw * (tef_hi - tef_lo))

            if vuln_hi == vuln_lo:
                vulnerability = pm.Deterministic("vulnerability", pm.math.constant(vuln_lo))
            else:
                a, b = _pert_to_beta_shape(vuln_lo, vuln_mode, vuln_hi)
                vuln_raw = pm.Beta("vuln_raw", alpha=a, beta=b)
                vulnerability = pm.Deterministic(
                    "vulnerability", vuln_lo + vuln_raw * (vuln_hi - vuln_lo)
                )

            if pl_hi == pl_lo:
                primary_loss = pm.Deterministic("primary_loss_magnitude", pm.math.constant(pl_lo))
            else:
                a, b = _pert_to_beta_shape(pl_lo, pl_mode, pl_hi)
                pl_raw = pm.Beta("pl_raw", alpha=a, beta=b)
                primary_loss = pm.Deterministic(
                    "primary_loss_magnitude", pl_lo + pl_raw * (pl_hi - pl_lo)
                )

            if has_secondary:
                if slef_hi == slef_lo:
                    slef = pm.Deterministic("secondary_loss_event_frequency", pm.math.constant(slef_lo))
                else:
                    a, b = _pert_to_beta_shape(slef_lo, slef_mode, slef_hi)
                    slef_raw = pm.Beta("slef_raw", alpha=a, beta=b)
                    slef = pm.Deterministic(
                        "secondary_loss_event_frequency", slef_lo + slef_raw * (slef_hi - slef_lo)
                    )

                if slm_hi == slm_lo:
                    slm = pm.Deterministic("secondary_loss_magnitude", pm.math.constant(slm_lo))
                else:
                    a, b = _pert_to_beta_shape(slm_lo, slm_mode, slm_hi)
                    slm_raw = pm.Beta("slm_raw", alpha=a, beta=b)
                    slm = pm.Deterministic(
                        "secondary_loss_magnitude", slm_lo + slm_raw * (slm_hi - slm_lo)
                    )
                secondary_loss = pm.Deterministic("secondary_loss", slef * slm)
            else:
                secondary_loss = 0.0

            lef = pm.Deterministic("loss_event_frequency", tef * vulnerability)
            loss_magnitude = pm.Deterministic("loss_magnitude", primary_loss + secondary_loss)
            pm.Deterministic("annual_loss", lef * loss_magnitude)

            idata = pm.sample_prior_predictive(draws=n_iterations, random_seed=seed)

        prior = idata.prior
        annual_losses = np.asarray(prior["annual_loss"].values).reshape(-1)

        named_samples = {
            "threat_event_frequency": np.asarray(prior["threat_event_frequency"].values).reshape(-1),
            "vulnerability": np.asarray(prior["vulnerability"].values).reshape(-1),
            "primary_loss_magnitude": np.asarray(prior["primary_loss_magnitude"].values).reshape(-1),
        }
        if has_secondary:
            named_samples["secondary_loss_event_frequency"] = np.asarray(
                prior["secondary_loss_event_frequency"].values
            ).reshape(-1)
            named_samples["secondary_loss_magnitude"] = np.asarray(
                prior["secondary_loss_magnitude"].values
            ).reshape(-1)

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
        if methodology not in ("monte_carlo", "fair", "fair_bayesian"):
            raise ValueError("'methodology' must be 'monte_carlo', 'fair', or 'fair_bayesian'")
        if not isinstance(input_parameters, dict) or not input_parameters:
            raise ValueError("'input_parameters' must be a non-empty object")
        if n_iterations < 1000:
            raise ValueError("'n_iterations' must be >= 1000 for a statistically meaningful simulation")

        rng = np.random.default_rng()

        if methodology == "fair":
            annual_losses, named_samples = self._simulate_fair(input_parameters, n_iterations, rng)
        elif methodology == "fair_bayesian":
            annual_losses, named_samples = self._simulate_fair_bayesian(input_parameters, n_iterations, rng)
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
