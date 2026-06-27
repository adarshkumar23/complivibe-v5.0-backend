"""Pillar 2 routers."""

from app.ai_governance.routers import (
    approval_envelopes,
    ai_reviews,
    ai_risk_assessments,
    ai_systems,
    eu_act_workflows,
    guardrails,
    iso42001,
    risk_signals,
    recommendations,
    diagnostics,
    contracts,
    monitoring,
    mlops,
    nist_rmf,
    shadow_ai,
    third_party_ai,
)

__all__ = [
    "approval_envelopes",
    "ai_reviews",
    "ai_risk_assessments",
    "ai_systems",
    "eu_act_workflows",
    "guardrails",
    "iso42001",
    "risk_signals",
    "recommendations",
    "diagnostics",
    "contracts",
    "monitoring",
    "mlops",
    "nist_rmf",
    "shadow_ai",
    "third_party_ai",
]
