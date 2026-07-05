from datetime import date

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.schemas.carbon_accounting import CarbonAccountingDashboard, CarbonEmissionsReadingIngest, CarbonEmissionsReadingRead
from app.services.carbon_accounting_service import CarbonAccountingService

router = APIRouter(prefix="/carbon-accounting", tags=["carbon-accounting"])


@router.post("/readings", response_model=CarbonEmissionsReadingRead, status_code=status.HTTP_201_CREATED)
def ingest_carbon_reading(
    payload: CarbonEmissionsReadingIngest,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> CarbonEmissionsReadingRead:
    service = CarbonAccountingService(db)
    org_id = service.resolve_org_by_api_key(x_complivibe_key or "")
    row = service.ingest_reading(org_id, payload)
    db.commit()
    db.refresh(row)
    return CarbonEmissionsReadingRead.model_validate(row)


@router.get("/dashboard", response_model=CarbonAccountingDashboard)
def carbon_dashboard(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("carbon_accounting:read")),
) -> CarbonAccountingDashboard:
    payload = CarbonAccountingService(db).dashboard(organization.id, start=start, end=end)
    return CarbonAccountingDashboard.model_validate(payload)
