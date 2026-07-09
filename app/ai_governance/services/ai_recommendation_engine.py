import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_bias_assessment import AIBiasAssessment
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system_risk_assessment import AISystemRiskAssessment

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
    def generate(self, org_id: uuid.UUID, system_id: uuid.UUID, db: Session) -> list[tuple[str, str, uuid.UUID | None]]:
        """Return recommendation candidates as ``(text, source_type, source_ref_id)`` tuples.

        Combines three independent, state-aware signal sources so that a system with an
        active drift breach or a failed bias assessment always gets a recommendation that
        reflects that live state -- not just a stale/generic set derived from the last
        completed risk assessment:
          * the latest completed risk assessment's high/critical dimension ratings
            (``source_type="risk_assessment"``)
          * any active monitoring config whose most recent reading breaches its threshold
            (``source_type="monitoring_breach"``)
          * any protected-attribute/metric combination whose latest bias assessment failed
            (``source_type="signal"``)
        """
        candidates: list[tuple[str, str, uuid.UUID | None]] = []
        seen: set[str] = set()

        def _add(text: str, source_type: str, source_ref_id: uuid.UUID | None) -> None:
            if text not in seen:
                seen.add(text)
                candidates.append((text, source_type, source_ref_id))

        assessment = db.execute(
            select(AISystemRiskAssessment)
            .where(
                AISystemRiskAssessment.organization_id == org_id,
                AISystemRiskAssessment.ai_system_id == system_id,
                AISystemRiskAssessment.status == "completed",
            )
            .order_by(AISystemRiskAssessment.completed_at.desc(), AISystemRiskAssessment.created_at.desc())
        ).scalars().first()

        if assessment is not None:
            dimensions_json = assessment.risk_dimensions_json if isinstance(assessment.risk_dimensions_json, dict) else {}
            dimension_ratings = {
                "bias": dimensions_json.get("bias"),
                "fairness": dimensions_json.get("fairness"),
                "explainability": dimensions_json.get("explainability"),
                "privacy": dimensions_json.get("privacy"),
                "misuse": dimensions_json.get("misuse"),
                "security": dimensions_json.get("security"),
            }
            for dimension, rating in dimension_ratings.items():
                if rating not in {"high", "critical"}:
                    continue
                templates = AI_RISK_RECOMMENDATION_TEMPLATES.get((dimension, rating)) or AI_RISK_RECOMMENDATION_TEMPLATES.get(
                    (dimension, "high"),
                    [],
                )
                for template in templates:
                    _add(template, "risk_assessment", assessment.id)

        # Active drift/monitoring breaches: any active config whose most recent reading is
        # outside the configured threshold represents a live, unresolved problem right now.
        configs = db.execute(
            select(AIMonitoringConfig).where(
                AIMonitoringConfig.organization_id == org_id,
                AIMonitoringConfig.ai_system_id == system_id,
                AIMonitoringConfig.is_active.is_(True),
                AIMonitoringConfig.deleted_at.is_(None),
            )
        ).scalars().all()
        for config in configs:
            latest_reading = db.execute(
                select(AIMonitoringReading)
                .where(AIMonitoringReading.config_id == config.id)
                .order_by(AIMonitoringReading.created_at.desc())
            ).scalars().first()
            if latest_reading is not None and not latest_reading.within_threshold:
                text = (
                    f"Active monitoring breach on {config.metric_type}: the latest reading "
                    "is outside the configured threshold -- investigate immediately and "
                    "determine root cause (e.g. drift, degradation) before further production use."
                )
                _add(text, "monitoring_breach", latest_reading.id)

        # Failed bias assessments: for each protected-attribute/metric combination, look at
        # only the most recent assessment -- a later passing re-test should not keep
        # generating a stale failure recommendation.
        bias_rows = db.execute(
            select(AIBiasAssessment)
            .where(
                AIBiasAssessment.organization_id == org_id,
                AIBiasAssessment.system_id == system_id,
            )
            .order_by(AIBiasAssessment.assessed_at.desc())
        ).scalars().all()
        latest_bias_by_key: dict[tuple[str, str], AIBiasAssessment] = {}
        for row in bias_rows:
            key = (row.protected_attribute, row.metric_name)
            if key not in latest_bias_by_key:
                latest_bias_by_key[key] = row
        for (protected_attribute, metric_name), row in latest_bias_by_key.items():
            if not row.passed:
                text = (
                    f"Bias assessment failed for protected attribute '{protected_attribute}' "
                    f"on metric '{metric_name}' -- conduct bias testing across all protected "
                    "attributes within 14 days and document a remediation plan."
                )
                _add(text, "signal", row.id)

        if not candidates:
            return [(text, "manual", None) for text in GENERIC_RECOMMENDATIONS]
        return candidates
