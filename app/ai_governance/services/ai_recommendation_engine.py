import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_risk_assessment import AIRiskAssessment

AI_RISK_RECOMMENDATION_TEMPLATES = {
    ("bias", "critical"): [
        "Immediately halt deployment and commission a comprehensive bias audit from an independent third party.",
        "Establish a bias remediation plan with measurable targets and a 30-day remediation deadline.",
        "Document all affected demographic groups and prepare for regulatory notification.",
    ],
    ("bias", "high"): [
        "Conduct bias testing across all protected attributes within 14 days.",
        "Implement bias monitoring configuration (AI monitoring config) for bias_parity_gap metric.",
        "Review and re-balance training data for underrepresented groups.",
    ],
    ("bias", "medium"): [
        "Schedule bias evaluation in the next periodic review cycle.",
        "Add bias_parity_gap to continuous monitoring configurations.",
    ],
    ("fairness", "critical"): [
        "Suspend high-stakes decisions made by this system pending fairness review.",
        "Engage affected stakeholders and document fairness criteria explicitly.",
    ],
    ("fairness", "high"): [
        "Compute demographic parity and equalized odds metrics and document results.",
        "Set fairness thresholds and configure monitoring for ongoing tracking.",
    ],
    ("explainability", "high"): [
        "Implement a model explanation layer (e.g. SHAP, LIME) for high-stakes decisions.",
        "Document the top-5 decision factors for all output categories.",
    ],
    ("privacy", "critical"): [
        "Immediately review data flows and halt processing of special category data without DPA.",
        "Complete a Data Protection Impact Assessment (DPIA) within 72 hours.",
    ],
    ("privacy", "high"): [
        "Document all personal data fields processed and their legal basis.",
        "Implement data minimization — remove processing of non-essential fields.",
    ],
    ("misuse", "critical"): [
        "Restrict system access immediately and conduct an internal investigation.",
        "Document the misuse scenario and escalate to the AI governance committee.",
    ],
    ("misuse", "high"): [
        "Define and document prohibited uses formally in the model card.",
        "Implement access controls to prevent unauthorized use patterns.",
    ],
    ("security", "critical"): [
        "Treat this as a security incident — initiate incident response process.",
        "Isolate model inference endpoints from untrusted input immediately.",
    ],
    ("security", "high"): [
        "Commission adversarial testing (prompt injection, data poisoning) within 30 days.",
        "Review and harden model artifact storage access controls.",
    ],
}

GENERIC_RECOMMENDATIONS = [
    "Review AI risk assessment results with the system owner and define action plan.",
    "Document all identified risks in the AI governance event log.",
    "Schedule a governance review within 14 days to address outstanding risks.",
]

CAVEAT = "These are suggestions for human review, not compliance determinations."


class AIRecommendationEngine:
    def generate(self, org_id: uuid.UUID, system_id: uuid.UUID, db: Session) -> list[str]:
        assessment = db.execute(
            select(AIRiskAssessment)
            .where(
                AIRiskAssessment.organization_id == org_id,
                AIRiskAssessment.ai_system_id == system_id,
                AIRiskAssessment.status == "completed",
            )
            .order_by(AIRiskAssessment.completed_at.desc(), AIRiskAssessment.created_at.desc())
        ).scalars().first()

        if assessment is None:
            return GENERIC_RECOMMENDATIONS

        recommendations: list[str] = []
        seen: set[str] = set()
        dimension_ratings = {
            "bias": assessment.bias_risk_rating,
            "fairness": assessment.fairness_risk_rating,
            "explainability": assessment.explainability_risk_rating,
            "privacy": assessment.privacy_risk_rating,
            "misuse": assessment.misuse_risk_rating,
            "security": assessment.security_risk_rating,
        }

        for dimension, rating in dimension_ratings.items():
            if rating not in {"high", "critical"}:
                continue
            templates = AI_RISK_RECOMMENDATION_TEMPLATES.get((dimension, rating)) or AI_RISK_RECOMMENDATION_TEMPLATES.get(
                (dimension, "high"),
                [],
            )
            for template in templates:
                if template not in seen:
                    seen.add(template)
                    recommendations.append(template)

        return recommendations or GENERIC_RECOMMENDATIONS
