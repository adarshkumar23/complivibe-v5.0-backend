from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.platform.schemas.report_sharing import (
    ShareLinkCreate,
    ShareLinkListItem,
    ShareLinkResponse,
    SharePasswordVerifyRequest,
    SharePasswordVerifyResponse,
)
from app.platform.services.report_share_service import ReportShareService

router = APIRouter(prefix="/reports", tags=["report-sharing"])


@router.post("/share", response_model=ShareLinkResponse)
def create_share_link(
    payload: ShareLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:share")),
) -> ShareLinkResponse:
    # Minting a share link is data EGRESS, not a read: it produces a URL that serves
    # report contents to whoever holds it, outside the app's authentication entirely.
    # It was gated on `compliance:read`, which every system role holds -- including
    # auditor and readonly, whose whole posture is that they cannot export anything.
    # Listing and revoking links stay on compliance:read; only creation is restricted.
    service = ReportShareService()
    row = service.create_share_link(
        org_id=organization.id,
        created_by=current_user.id,
        report_type=payload.report_type,
        report_params=payload.report_params,
        expires_hours=payload.expires_hours,
        password=payload.password,
        max_views=payload.max_views,
        recipient_email=payload.recipient_email,
        watermark_text=payload.watermark_text,
        db=db,
        base_url=str(request.base_url),
    )
    db.commit()
    return ShareLinkResponse.model_validate(row)


@router.get("/shared-links", response_model=list[ShareLinkListItem])
def list_share_links(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[ShareLinkListItem]:
    rows = ReportShareService().list_org_link_payloads(organization.id, db)
    return [ShareLinkListItem.model_validate(row) for row in rows]


@router.delete("/shared-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> Response:
    ReportShareService().revoke_link(
        org_id=organization.id,
        link_id=link_id,
        user_id=current_user.id,
        db=db,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/shared/{token}")
def access_shared_report(
    token: str,
    password: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    result = ReportShareService().access_shared_report(token=token, password=password, db=db)
    db.commit()
    return result


@router.post("/shared/{token}/verify", response_model=SharePasswordVerifyResponse)
@rate_limiter.limiter.limit("10/minute")
def verify_share_password(
    token: str,
    payload: SharePasswordVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SharePasswordVerifyResponse:
    valid = ReportShareService().verify_password(token=token, password=payload.password, db=db)
    db.commit()
    return SharePasswordVerifyResponse(valid=valid)
