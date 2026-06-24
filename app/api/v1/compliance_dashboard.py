from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.services.compliance_dashboard_service import ComplianceDashboardService

router = APIRouter(prefix="/compliance/dashboard", tags=["compliance_dashboard"])


@router.get("/posture-summary")
def posture_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> dict:
    return ComplianceDashboardService(db).posture_summary(organization.id)


@router.get("/framework-readiness")
def framework_readiness(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[dict]:
    return ComplianceDashboardService(db).framework_readiness(organization.id)


@router.get("/control-health")
def control_health(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> dict:
    return ComplianceDashboardService(db).control_health(organization.id)


@router.get("/risk-heatmap")
def risk_heatmap(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> dict:
    return ComplianceDashboardService(db).risk_heatmap(organization.id)


@router.get("/recent-activity")
def recent_activity(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[dict]:
    return ComplianceDashboardService(db).recent_activity(organization.id, limit)
