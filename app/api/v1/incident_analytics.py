from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.compliance.services.classification_service import ClassificationService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.schemas.incident_classification import IncidentAnalyticsRead

router = APIRouter(prefix="/compliance/incidents", tags=["incident-analytics"])


@router.get("/by-category", response_model=IncidentAnalyticsRead)
def incidents_by_category(
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> IncidentAnalyticsRead:
    payload = ClassificationService(db).get_incidents_by_category(organization.id, category=category)
    return IncidentAnalyticsRead(**payload)
