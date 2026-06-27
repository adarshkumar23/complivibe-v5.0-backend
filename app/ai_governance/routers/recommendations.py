import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai_governance.schemas.signals_recommendations_diagnostics import AIRiskRecommendationRead
from app.ai_governance.services.ai_recommendation_service import AIRecommendationService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/recommendations", tags=["ai-governance-recommendations"])


@router.post("/{rec_id}/apply", response_model=AIRiskRecommendationRead)
def apply_recommendation(
    rec_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskRecommendationRead:
    row = AIRecommendationService(db).apply_recommendation(organization.id, rec_id, membership.user_id)
    db.commit()
    db.refresh(row)
    return AIRiskRecommendationRead.model_validate(row)


@router.post("/{rec_id}/dismiss", response_model=AIRiskRecommendationRead)
def dismiss_recommendation(
    rec_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskRecommendationRead:
    row = AIRecommendationService(db).dismiss_recommendation(organization.id, rec_id, membership.user_id)
    db.commit()
    db.refresh(row)
    return AIRiskRecommendationRead.model_validate(row)
