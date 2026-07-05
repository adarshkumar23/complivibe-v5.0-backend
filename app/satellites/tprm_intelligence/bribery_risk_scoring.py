from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bribery_risk_assessment import BriberyRiskAssessment
from app.models.organization import Organization
from app.models.vendor import Vendor

# Grounded scoring methodology (documented at model definition too):
#   - UK Bribery Act 2010 s.7 "adequate procedures" guidance (gov.uk MoJ) --
#     six principles including risk assessment and monitoring/review.
#   - FCPA-aligned third-party risk factors (DOJ/SEC FCPA Resource Guide):
#     jurisdiction corruption risk via Transparency International CPI,
#     PEP exposure, gifts/hospitality patterns, and industry risk.
#
# This is an illustrative, documented weighting scaffold -- NOT a
# regulator-prescribed formula. Weights should be periodically reviewed
# per MoJ Principle 6 (Monitoring and Review).
VALID_PEP_EXPOSURE = ("none", "indirect", "direct")

PEP_MULTIPLIER = {
    "none": 1.0,
    "indirect": 1.5,
    "direct": 2.0,
}

# Gift/hospitality threshold (USD) above which a single instance is treated
# as maximal risk regardless of frequency -- illustrative, not a fixed legal
# bright line (jurisdictions vary; document/tune per organization policy).
GIFT_VALUE_HIGH_RISK_THRESHOLD_USD = 250.0

# Industries commonly flagged as elevated ABC risk per FCPA enforcement
# patterns (extractives, defense, construction/infrastructure,
# healthcare/pharma, government contracting). Free text is accepted; this
# set only affects the industry_risk component when matched (case-insensitive).
HIGH_RISK_INDUSTRIES = {
    "extractives",
    "oil_and_gas",
    "mining",
    "defense",
    "construction",
    "infrastructure",
    "healthcare",
    "pharma",
    "pharmaceuticals",
    "government_contracting",
}

MEDIUM_RISK_INDUSTRIES = {
    "financial_services",
    "telecommunications",
    "energy",
    "logistics",
}

WEIGHTS = {
    "jurisdiction": 0.35,
    "pep": 0.25,
    "gift_hospitality": 0.15,
    "industry": 0.25,
}

# When jurisdiction_cpi_score is unknown, treat jurisdiction risk
# conservatively (elevated/unknown risk) rather than assuming a clean
# jurisdiction (which would understate risk) -- consistent with a
# risk-based, precautionary approach to third-party due diligence.
UNKNOWN_JURISDICTION_RISK_DEFAULT = 0.7

HIGH_RISK_TIER_THRESHOLD = 0.6
MEDIUM_RISK_TIER_THRESHOLD = 0.35


def _industry_risk(industry_category: str | None) -> float:
    if not industry_category:
        return 0.2
    normalized = industry_category.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in HIGH_RISK_INDUSTRIES:
        return 1.0
    if normalized in MEDIUM_RISK_INDUSTRIES:
        return 0.5
    return 0.2


def _gift_hospitality_risk(gift_hospitality_log: list[dict[str, Any]] | None) -> tuple[float, dict[str, Any]]:
    entries = gift_hospitality_log or []
    for entry in entries:
        value = entry.get("value_usd")
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError("gift_hospitality_log entry value_usd must be numeric")
        if value < 0:
            raise ValueError("gift_hospitality_log entry value_usd must not be negative")

    if not entries:
        return 0.0, {"reason": "no gift/hospitality entries logged"}

    above_threshold = [
        e for e in entries if e.get("value_usd") is not None and float(e["value_usd"]) >= GIFT_VALUE_HIGH_RISK_THRESHOLD_USD
    ]
    if above_threshold:
        return 1.0, {"reason": "at least one entry at/above threshold", "threshold_usd": GIFT_VALUE_HIGH_RISK_THRESHOLD_USD, "count_above_threshold": len(above_threshold)}
    return 0.5, {"reason": "entries logged, all below threshold", "threshold_usd": GIFT_VALUE_HIGH_RISK_THRESHOLD_USD, "entry_count": len(entries)}


def _risk_tier(risk_score: float) -> str:
    if risk_score >= HIGH_RISK_TIER_THRESHOLD:
        return "high"
    if risk_score >= MEDIUM_RISK_TIER_THRESHOLD:
        return "medium"
    return "low"


class BriberyRiskScoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def compute_risk_assessment(
        self,
        organization: Organization,
        vendor: Vendor,
        *,
        jurisdiction: str,
        jurisdiction_cpi_score: int | None,
        pep_exposure: str,
        gift_hospitality_log: list[dict[str, Any]] | None,
        industry_category: str | None,
        computed_by_user_id=None,
    ) -> BriberyRiskAssessment:
        if pep_exposure not in VALID_PEP_EXPOSURE:
            raise ValueError(f"pep_exposure must be one of {VALID_PEP_EXPOSURE}, got {pep_exposure!r}")

        if jurisdiction_cpi_score is not None:
            if not (0 <= jurisdiction_cpi_score <= 100):
                raise ValueError("jurisdiction_cpi_score must be between 0 and 100")
            jurisdiction_risk = (100 - jurisdiction_cpi_score) / 100
            jurisdiction_source = "provided_cpi_score"
        else:
            jurisdiction_risk = UNKNOWN_JURISDICTION_RISK_DEFAULT
            jurisdiction_source = "unknown_cpi_conservative_default"

        pep_multiplier = PEP_MULTIPLIER[pep_exposure]
        pep_component = pep_multiplier / 2.0

        gift_hospitality_risk, gift_detail = _gift_hospitality_risk(gift_hospitality_log)

        industry_risk = _industry_risk(industry_category)

        raw_score = (
            WEIGHTS["jurisdiction"] * jurisdiction_risk
            + WEIGHTS["pep"] * pep_component
            + WEIGHTS["gift_hospitality"] * gift_hospitality_risk
            + WEIGHTS["industry"] * industry_risk
        )
        risk_score = max(0.0, min(1.0, raw_score))
        risk_tier = _risk_tier(risk_score)

        scoring_breakdown_json = {
            "weights": WEIGHTS,
            "components": {
                "jurisdiction_risk": {
                    "value": jurisdiction_risk,
                    "weight": WEIGHTS["jurisdiction"],
                    "weighted_contribution": WEIGHTS["jurisdiction"] * jurisdiction_risk,
                    "source": jurisdiction_source,
                    "jurisdiction_cpi_score": jurisdiction_cpi_score,
                },
                "pep_component": {
                    "value": pep_component,
                    "weight": WEIGHTS["pep"],
                    "weighted_contribution": WEIGHTS["pep"] * pep_component,
                    "pep_exposure": pep_exposure,
                    "pep_multiplier": pep_multiplier,
                },
                "gift_hospitality_risk": {
                    "value": gift_hospitality_risk,
                    "weight": WEIGHTS["gift_hospitality"],
                    "weighted_contribution": WEIGHTS["gift_hospitality"] * gift_hospitality_risk,
                    "detail": gift_detail,
                },
                "industry_risk": {
                    "value": industry_risk,
                    "weight": WEIGHTS["industry"],
                    "weighted_contribution": WEIGHTS["industry"] * industry_risk,
                    "industry_category": industry_category,
                },
            },
            "raw_score": raw_score,
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "methodology": (
                "Illustrative weighting scaffold aligned with FCPA/UK Bribery Act "
                "2010 s.7 risk factors (jurisdiction CPI, PEP exposure, "
                "gifts/hospitality, industry) -- not a regulator-prescribed "
                "formula. Review periodically per MoJ Principle 6 (Monitoring "
                "and Review)."
            ),
        }

        row = BriberyRiskAssessment(
            organization_id=organization.id,
            vendor_id=vendor.id,
            jurisdiction=jurisdiction,
            jurisdiction_cpi_score=jurisdiction_cpi_score,
            pep_exposure=pep_exposure,
            gift_hospitality_log_json=gift_hospitality_log,
            industry_category=industry_category,
            risk_score=risk_score,
            risk_tier=risk_tier,
            scoring_breakdown_json=scoring_breakdown_json,
            computed_by_user_id=computed_by_user_id,
            # Set explicitly (rather than relying solely on the DB
            # server_default) so ordering by computed_at is reliable even on
            # backends (e.g. SQLite) whose CURRENT_TIMESTAMP has only
            # second-level resolution.
            computed_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest_assessment(self, organization_id, vendor_id) -> BriberyRiskAssessment | None:
        return self.db.execute(
            select(BriberyRiskAssessment)
            .where(
                BriberyRiskAssessment.organization_id == organization_id,
                BriberyRiskAssessment.vendor_id == vendor_id,
            )
            .order_by(BriberyRiskAssessment.computed_at.desc(), BriberyRiskAssessment.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_assessments(self, organization_id, vendor_id) -> list[BriberyRiskAssessment]:
        return list(
            self.db.execute(
                select(BriberyRiskAssessment)
                .where(
                    BriberyRiskAssessment.organization_id == organization_id,
                    BriberyRiskAssessment.vendor_id == vendor_id,
                )
                .order_by(BriberyRiskAssessment.computed_at.desc(), BriberyRiskAssessment.id.desc())
            ).scalars().all()
        )
