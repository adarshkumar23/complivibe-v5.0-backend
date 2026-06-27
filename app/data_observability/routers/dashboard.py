from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.data_observability.schemas.dashboard import DataObservabilityDashboardRead
from app.data_observability.services.dashboard_service import DataObservabilityDashboardService
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/data-observability/dashboard", tags=["data-observability-dashboard"])


@router.get("", response_model=DataObservabilityDashboardRead)
def get_data_observability_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataObservabilityDashboardRead:
    payload = DataObservabilityDashboardService(db).get_dashboard(organization.id)
    return DataObservabilityDashboardRead.model_validate(payload)
