from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.data_observability.schemas.data_obligations import DataObligationCoverageRead
from app.data_observability.services.data_obligation_service import DataObligationService
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/data-observability", tags=["data-observability-obligation-coverage"])


@router.get("/obligation-coverage", response_model=DataObligationCoverageRead)
def get_obligation_coverage_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataObligationCoverageRead:
    payload = DataObligationService(db).get_coverage_summary(organization.id)
    return DataObligationCoverageRead.model_validate(payload)
