import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_system import AISystem


def _get_org_ai_system(ai_system_id: uuid.UUID, organization_id: uuid.UUID, db: Session) -> AISystem:
    """Fetch an AI system scoped to the requesting organization.

    Must never fall back to an unscoped db.get() lookup: that would let one
    organization draft content (model cards, risk narratives) seeded with
    another organization's confidential AI system name/purpose/risk data --
    a cross-tenant data leak. Raise 404 rather than silently returning None
    so the caller can't distinguish "not found" from "belongs to someone
    else", and so no data ever reaches the prompt/draft text.
    """
    from fastapi import HTTPException, status

    system = db.execute(
        select(AISystem).where(
            AISystem.id == ai_system_id,
            AISystem.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
    return system


def build_risk_assessment_context(ai_system_id: uuid.UUID, organization_id: uuid.UUID, db: Session) -> dict:
    """Build safe governance metadata context for AI risk-assessment drafting."""
    system = _get_org_ai_system(ai_system_id, organization_id, db)
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
        "system_name": system.name,
        "system_purpose": system.purpose if system.purpose else "Not specified",
        "risk_tier": classification.risk_tier if classification else "unassessed",
        "bias_rating": assessment.bias_risk_rating if assessment else "not_assessed",
        "overall_risk_score": float(assessment.overall_risk_score)
        if assessment and assessment.overall_risk_score is not None
        else None,
    }


def build_model_card_context(ai_system_id: uuid.UUID, organization_id: uuid.UUID, db: Session) -> dict:
    """Build safe governance metadata context for model-card drafting."""
    system = _get_org_ai_system(ai_system_id, organization_id, db)
    classification = db.execute(
        select(AIRiskClassification).where(AIRiskClassification.ai_system_id == ai_system_id)
    ).scalar_one_or_none()

    return {
        "system_name": system.name,
        "purpose": system.purpose if system.purpose else "Not specified",
        "risk_tier": classification.risk_tier if classification else "unassessed",
        "deployment_context": system.deployment_status,
        "affected_population": system.affected_population if system.affected_population else "Not specified",
    }
