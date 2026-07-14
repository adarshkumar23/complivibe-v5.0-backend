import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.cookies import (
    BannerConfigCreate,
    BannerConfigRead,
    CookieCreate,
    CookieRead,
    CookieScanReport,
    CookieScanResult,
    CookieUpdate,
    PublicBannerRead,
)
from app.privacy.services.cookie_service import CookieService

router = APIRouter(prefix="/privacy", tags=["privacy-cookies"])


@router.post("/cookie-registry/scan-report", response_model=CookieScanResult, status_code=status.HTTP_201_CREATED)
def receive_cookie_scan_report(
    payload: CookieScanReport,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> CookieScanResult:
    service = CookieService(db)
    org_id = service.resolve_org_by_api_key(x_complivibe_key or "")
    result = service.process_scan_report(
        org_id=org_id,
        domain=payload.domain,
        cookies=[item.model_dump() for item in payload.cookies],
        scanned_at=payload.scanned_at,
    )
    db.commit()
    return CookieScanResult.model_validate(result)


@router.get("/consent-banner/{org_slug}", response_model=PublicBannerRead)
def get_public_banner(
    org_slug: str,
    db: Session = Depends(get_db),
) -> PublicBannerRead:
    payload = CookieService(db).get_public_banner(org_slug)
    return PublicBannerRead.model_validate(payload)


@router.post("/cookies", response_model=CookieRead, status_code=status.HTTP_201_CREATED)
def create_cookie(
    payload: CookieCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> CookieRead:
    row = CookieService(db).create_cookie(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return CookieRead.model_validate(row)


@router.get("/cookies", response_model=list[CookieRead])
def list_cookies(
    category: str | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[CookieRead]:
    rows = CookieService(db).list_cookies(organization.id, category=category, is_active=is_active)
    return [CookieRead.model_validate(row) for row in rows]


@router.get("/cookies/{cookie_id}", response_model=CookieRead)
def get_cookie(
    cookie_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> CookieRead:
    row = CookieService(db).get_cookie(organization.id, cookie_id)
    return CookieRead.model_validate(row)


@router.patch("/cookies/{cookie_id}", response_model=CookieRead)
def update_cookie(
    cookie_id: uuid.UUID,
    payload: CookieUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> CookieRead:
    row = CookieService(db).update_cookie(organization.id, cookie_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return CookieRead.model_validate(row)


@router.post("/banner-config", response_model=BannerConfigRead)
def create_or_update_banner(
    payload: BannerConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> BannerConfigRead:
    row = CookieService(db).create_or_update_banner(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return BannerConfigRead.model_validate(row)


@router.get("/banner-config", response_model=BannerConfigRead | None)
def get_banner_config(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> BannerConfigRead | None:
    row = CookieService(db).get_banner_config(organization.id)
    if row is None:
        return None
    return BannerConfigRead.model_validate(row)
