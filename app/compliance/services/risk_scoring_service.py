import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.org_risk_settings import OrgRiskSettings
from app.models.risk import Risk

# Control statuses that don't represent an active mitigation in effect.
_CONTROL_NOT_RELEVANT_STATUSES = {"not_applicable", "archived"}


class RiskScoringService:
    DEFAULT_FINANCIAL_WEIGHT = Decimal("0.400")
    DEFAULT_BRAND_WEIGHT = Decimal("0.300")
    DEFAULT_OPERATIONAL_WEIGHT = Decimal("0.300")

    @classmethod
    def get_or_create_org_settings(cls, org_id: uuid.UUID, db: Session) -> OrgRiskSettings:
        row = db.execute(
            select(OrgRiskSettings).where(OrgRiskSettings.organization_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row

        row = OrgRiskSettings(
            organization_id=org_id,
            financial_weight=cls.DEFAULT_FINANCIAL_WEIGHT,
            brand_weight=cls.DEFAULT_BRAND_WEIGHT,
            operational_weight=cls.DEFAULT_OPERATIONAL_WEIGHT,
        )
        db.add(row)
        db.flush()
        return row

    # Midpoint of the 1-5 likelihood scale. Factor-based scoring treats likelihood as a
    # frequency multiplier around this midpoint (FAIR-style loss-magnitude x frequency
    # composition, simplified to a single continuous adjustment rather than a full Monte
    # Carlo simulation): likelihood == LIKELIHOOD_MIDPOINT leaves the weighted factor
    # composite unchanged, likelihood below it discounts the composite, and likelihood
    # above it amplifies it.
    LIKELIHOOD_MIDPOINT = Decimal(3)

    @staticmethod
    def _scale_raw_score(raw_score: Decimal) -> int:
        scaled_score = round(float(raw_score) * 5)
        # Keep exact whole-number weighted sums below 5.0 in the lower 1-25 bucket.
        if float(raw_score).is_integer() and 1 < float(raw_score) < 5:
            scaled_score -= 1
        return int(max(1, min(25, scaled_score)))

    @staticmethod
    def _factor_raw_composite(risk: Risk, org_settings: OrgRiskSettings) -> Decimal:
        if risk.financial_impact is None or risk.brand_impact is None or risk.operational_impact is None:
            raise ValueError(
                "Factor-based scoring requires financial_impact, brand_impact, and operational_impact to be set."
            )
        return (
            (Decimal(risk.financial_impact) * org_settings.financial_weight)
            + (Decimal(risk.brand_impact) * org_settings.brand_weight)
            + (Decimal(risk.operational_impact) * org_settings.operational_weight)
        )

    @classmethod
    def _factor_raw_score(cls, raw_composite: Decimal, likelihood: int) -> Decimal:
        """Apply the likelihood frequency multiplier to the weighted factor composite."""
        return raw_composite * (Decimal(likelihood) / cls.LIKELIHOOD_MIDPOINT)

    @classmethod
    def compute_score(cls, risk: Risk, org_settings: OrgRiskSettings) -> int:
        method = risk.composite_score_method or "standard"
        if method != "factor_based":
            return int(risk.likelihood * risk.impact)

        raw_composite = cls._factor_raw_composite(risk, org_settings)
        raw_score = cls._factor_raw_score(raw_composite, risk.likelihood)
        return cls._scale_raw_score(raw_score)

    @classmethod
    def compute_residual_score(
        cls,
        risk: Risk,
        org_settings: OrgRiskSettings,
        *,
        residual_likelihood: int | None,
        residual_impact: int | None,
        inherent_score: int,
    ) -> int | None:
        """Derive residual_score using the SAME scoring methodology as the risk's
        active composite_score_method, so factor_based risks get factor-based
        residual scoring (not the plain likelihood*impact multiplication that only
        applies to standard risks).
        """
        if residual_likelihood is None or residual_impact is None:
            return None

        method = risk.composite_score_method or "standard"
        if method == "factor_based":
            raw_composite = cls._factor_raw_composite(risk, org_settings)
            raw_score = cls._factor_raw_score(raw_composite, residual_likelihood)
            residual_score = cls._scale_raw_score(raw_score)
        else:
            residual_score = residual_likelihood * residual_impact

        # residual (post-control) risk can never logically exceed inherent (pre-control) risk.
        return min(residual_score, inherent_score)

    @classmethod
    def compute_residual(
        cls,
        risk: Risk,
        linked_controls: list[Control],
        inherent_score: int,
        org_settings: OrgRiskSettings,
    ) -> tuple[int, int, int]:
        """Derive residual (post-control) likelihood/impact/score from currently linked controls.

        inherent_score is deliberately left untouched by control state elsewhere (it's the
        pre-control baseline, per standard risk terminology, and is covered by existing tests
        in test_risk_recalculation_a15.py asserting it only ever re-derives from the risk's own
        likelihood/impact). Controls are modeled here as reducing likelihood (probability of the
        risk materializing), not impact (severity of consequence if it does) -- the conventional
        split between preventive/detective control effect and consequence severity.

        This function is always a full, deterministic recompute from current linked-control
        state (never incremental), consistent with how inherent-score recalculation already
        works. Any manual residual_likelihood/residual_impact set via a direct risk PATCH will
        be overwritten the next time a linked control/evidence/vendor event fires -- this is an
        auto-managed field, not a one-time manual override.

        residual_score is computed via the same methodology basis as the risk's active
        composite_score_method (see `compute_residual_score`) and clamped to
        inherent_score, since a post-control residual risk can never logically exceed the
        pre-control inherent risk level.
        """
        relevant = [c for c in linked_controls if c.status not in _CONTROL_NOT_RELEVANT_STATUSES]
        implemented = [c for c in relevant if c.status == "implemented"]

        if not implemented:
            # No controls, or none of the linked controls are actually effective yet:
            # residual mirrors inherent (nothing is currently mitigating this risk).
            residual_likelihood = risk.likelihood
        else:
            reduction = min(len(implemented), 2)
            if any(c.criticality == "critical" for c in implemented):
                reduction += 1
            residual_likelihood = max(1, risk.likelihood - reduction)

        residual_impact = risk.impact
        residual_score = cls.compute_residual_score(
            risk,
            org_settings,
            residual_likelihood=residual_likelihood,
            residual_impact=residual_impact,
            inherent_score=inherent_score,
        )
        return residual_likelihood, residual_impact, residual_score

    @classmethod
    def compute_breakdown(cls, risk: Risk, org_settings: OrgRiskSettings) -> dict:
        method = risk.composite_score_method or "standard"
        if method != "factor_based":
            return {
                "method": "standard",
                "likelihood": int(risk.likelihood),
                "impact": int(risk.impact),
                "score": int(risk.inherent_score),
                "residual_likelihood": risk.residual_likelihood,
                "residual_impact": risk.residual_impact,
                "residual_score": risk.residual_score,
            }

        if risk.financial_impact is None or risk.brand_impact is None or risk.operational_impact is None:
            raise ValueError(
                "Factor-based scoring requires financial_impact, brand_impact, and operational_impact to be set."
            )

        financial = float(Decimal(risk.financial_impact) * org_settings.financial_weight)
        brand = float(Decimal(risk.brand_impact) * org_settings.brand_weight)
        operational = float(Decimal(risk.operational_impact) * org_settings.operational_weight)
        raw_score = financial + brand + operational
        likelihood_multiplier = float(Decimal(risk.likelihood) / cls.LIKELIHOOD_MIDPOINT)

        def _contribution(value: int, weight: Decimal) -> dict:
            contribution = float(Decimal(value) * weight)
            contribution_pct = (contribution / raw_score * 100.0) if raw_score > 0 else 0.0
            return {
                "impact_value": value,
                "weight": float(weight),
                "contribution": contribution,
                "contribution_pct": contribution_pct,
            }

        return {
            "method": "factor_based",
            "likelihood": int(risk.likelihood),
            "factors": {
                "financial": _contribution(risk.financial_impact, org_settings.financial_weight),
                "brand": _contribution(risk.brand_impact, org_settings.brand_weight),
                "operational": _contribution(risk.operational_impact, org_settings.operational_weight),
            },
            "raw_score": raw_score,
            "likelihood_multiplier": likelihood_multiplier,
            "raw_score_after_likelihood": raw_score * likelihood_multiplier,
            "scaled_score": cls.compute_score(risk, org_settings),
            "org_weights": {
                "financial": float(org_settings.financial_weight),
                "brand": float(org_settings.brand_weight),
                "operational": float(org_settings.operational_weight),
            },
            "residual_likelihood": risk.residual_likelihood,
            "residual_impact": risk.residual_impact,
            "residual_score": risk.residual_score,
        }
