import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.risk_graph_service import RiskGraphService
from app.compliance.services.risk_scoring_service import RiskScoringService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.repositories.risk_repository import RiskRepository

router = APIRouter(prefix="/compliance/risks", tags=["risks"])


@router.get("/{risk_id}/score-breakdown", response_model=dict)
def get_risk_score_breakdown_compliance_alias(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> dict:
    risk = RiskRepository(db).get_by_id(risk_id)
    if risk is None or risk.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    settings = RiskScoringService.get_or_create_org_settings(organization.id, db)
    return RiskScoringService.compute_breakdown(risk, settings)


@router.get("/{risk_id}/graph", response_model=dict)
def get_risk_graph_compliance_alias(
    risk_id: uuid.UUID,
    depth: int = Query(default=1, ge=1, le=2),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> dict:
    risk = RiskRepository(db).get_by_id(risk_id)
    if risk is None or risk.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    return RiskGraphService.build(risk_id=risk.id, org_id=organization.id, depth=depth, db=db)
