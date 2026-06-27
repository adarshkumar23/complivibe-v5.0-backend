import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_system import AISystem


def build_risk_assessment_context(ai_system_id: uuid.UUID, db: Session) -> dict:
    """Build safe governance metadata context for AI risk-assessment drafting."""
    system = db.get(AISystem, ai_system_id)
    classification = db.execute(
        select(AIRiskClassification).where(AIRiskClassification.ai_system_id == ai_system_id)
    ).scalar_one_or_none()
    assessment = db.execute(
        select(AIRiskAssessment)
        .where(
            AIRiskAssessment.ai_system_id == ai_system_id,
            AIRiskAssessment.status == "completed",
        )
        .order_by(AIRiskAssessment.completed_at.desc())
    ).scalars().first()

    return {
        "system_name": system.name if system else "Unknown",
        "system_purpose": system.purpose if system and system.purpose else "Not specified",
        "risk_tier": classification.risk_tier if classification else "unassessed",
        "bias_rating": assessment.bias_risk_rating if assessment else "not_assessed",
        "overall_risk_score": float(assessment.overall_risk_score)
        if assessment and assessment.overall_risk_score is not None
        else None,
    }


def build_model_card_context(ai_system_id: uuid.UUID, db: Session) -> dict:
    """Build safe governance metadata context for model-card drafting."""
    system = db.get(AISystem, ai_system_id)
    classification = db.execute(
        select(AIRiskClassification).where(AIRiskClassification.ai_system_id == ai_system_id)
    ).scalar_one_or_none()

    return {
        "system_name": system.name if system else "Unknown",
        "purpose": system.purpose if system and system.purpose else "Not specified",
        "risk_tier": classification.risk_tier if classification else "unassessed",
        "deployment_context": system.deployment_status if system else "unknown",
        "affected_population": system.affected_population if system and system.affected_population else "Not specified",
    }
