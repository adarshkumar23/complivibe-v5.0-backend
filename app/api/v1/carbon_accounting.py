from datetime import date

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.carbon_accounting import (
    CarbonAccountingApiKeyProvisionResponse,
    CarbonAccountingDashboard,
    CarbonEmissionsReadingIngest,
    CarbonEmissionsReadingRead,
)
from app.services.carbon_accounting_service import CarbonAccountingService

router = APIRouter(prefix="/carbon-accounting", tags=["carbon-accounting"])


@router.post("/api-key", response_model=CarbonAccountingApiKeyProvisionResponse)
def provision_carbon_accounting_api_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("carbon_accounting:write")),
) -> CarbonAccountingApiKeyProvisionResponse:
    """Provision (or rotate) this org's carbon-accounting ingest API key.

    Call this once before ingesting readings via POST /carbon-accounting/readings --
    that endpoint authenticates via the X-CompliVibe-Key header, and (unlike some
    other ingest features in this codebase) does NOT reuse any other integration's
    key. The returned key is shown only once; rotating replaces the previous key.
    """
    raw_key = CarbonAccountingService(db).provision_api_key(organization.id, current_user.id)
    db.commit()
    return CarbonAccountingApiKeyProvisionResponse(api_key=raw_key)


@router.post("/readings", response_model=CarbonEmissionsReadingRead, status_code=status.HTTP_201_CREATED)
def ingest_carbon_reading(
    payload: CarbonEmissionsReadingIngest,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> CarbonEmissionsReadingRead:
    """Machine/automated ingest: authenticated ONLY by the X-CompliVibe-Key header.

    For external systems pushing readings without an interactive session. The org is
    derived from the key. Interactive UI entry should use /readings/manual instead,
    which authenticates by the user's session and needs no ingest key in the browser.
    """
    service = CarbonAccountingService(db)
    org_id = service.resolve_org_by_api_key(x_complivibe_key or "")
    row = service.ingest_reading(org_id, payload)
    db.commit()
    db.refresh(row)
    return CarbonEmissionsReadingRead.model_validate(row)


@router.post("/readings/manual", response_model=CarbonEmissionsReadingRead, status_code=status.HTTP_201_CREATED)
def ingest_carbon_reading_manual(
    payload: CarbonEmissionsReadingIngest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("carbon_accounting:write")),
) -> CarbonEmissionsReadingRead:
    """Interactive/console reading entry for a signed-in user.

    Identical ingest to POST /readings, but authenticated by the user's session
    (cookie/bearer + CSRF) with org resolved from membership and gated on
    carbon_accounting:write. This exists so the UI never has to provision, cache in
    the browser, or transmit the machine X-CompliVibe-Key ingest credential -- the
    caller is already authenticated. The key-authed /readings endpoint remains for
    external/automated ingest.
    """
    _ = current_user
    service = CarbonAccountingService(db)
    row = service.ingest_reading(organization.id, payload)
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
