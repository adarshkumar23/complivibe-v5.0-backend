from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compliance.services.ai_governance_dashboard_service import AIGovernanceDashboardService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.schemas.ai_governance_dashboard import AIGovernanceDashboardRead

router = APIRouter(prefix="/ai-governance", tags=["ai-governance-dashboard"])


@router.get("/dashboard", response_model=AIGovernanceDashboardRead)
def get_ai_governance_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIGovernanceDashboardRead:
    payload = AIGovernanceDashboardService(db).get_dashboard(organization.id)
    return AIGovernanceDashboardRead(**payload)

