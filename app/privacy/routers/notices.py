import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.notices import (
    NoticeAcknowledgementRead,
    NoticeAcknowledgementStatus,
    PrivacyNoticeCreate,
    PrivacyNoticeRead,
    PrivacyNoticeUpdate,
)
from app.privacy.services.notice_service import NoticeService

router = APIRouter(prefix="/privacy/notices", tags=["privacy-notices"])


@router.post("", response_model=PrivacyNoticeRead, status_code=status.HTTP_201_CREATED)
def create_notice(
    payload: PrivacyNoticeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> PrivacyNoticeRead:
    row = NoticeService(db).create_notice(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return PrivacyNoticeRead.model_validate(row)


@router.get("", response_model=list[PrivacyNoticeRead])
def list_notices(
    status_filter: str | None = Query(default=None, alias="status"),
    language: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[PrivacyNoticeRead]:
    rows = NoticeService(db).list_notices(organization.id, status_filter=status_filter, language=language)
    return [PrivacyNoticeRead.model_validate(row) for row in rows]


@router.get("/active", response_model=PrivacyNoticeRead | None)
def get_active_notice(
    language: str = Query(default="en"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> PrivacyNoticeRead | None:
    row = NoticeService(db).get_active_notice(organization.id, language=language)
    if row is None:
        return None
    return PrivacyNoticeRead.model_validate(row)


@router.get("/active/languages", response_model=list[PrivacyNoticeRead])
def list_active_notice_languages(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[PrivacyNoticeRead]:
    rows = NoticeService(db).list_active_notice_languages(organization.id)
    return [PrivacyNoticeRead.model_validate(row) for row in rows]


@router.get("/{notice_id}", response_model=PrivacyNoticeRead)
def get_notice(
    notice_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> PrivacyNoticeRead:
    row = NoticeService(db).get_notice(organization.id, notice_id)
    return PrivacyNoticeRead.model_validate(row)


@router.patch("/{notice_id}", response_model=PrivacyNoticeRead)
def update_notice(
    notice_id: uuid.UUID,
    payload: PrivacyNoticeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> PrivacyNoticeRead:
    row = NoticeService(db).update_notice(organization.id, notice_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return PrivacyNoticeRead.model_validate(row)


@router.post("/{notice_id}/publish", response_model=PrivacyNoticeRead)
def publish_notice(
    notice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> PrivacyNoticeRead:
    row = NoticeService(db).publish_notice(organization.id, notice_id, current_user.id)
    db.commit()
    db.refresh(row)
    return PrivacyNoticeRead.model_validate(row)


@router.post("/{notice_id}/acknowledge", response_model=NoticeAcknowledgementRead)
def acknowledge_notice(
    notice_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> NoticeAcknowledgementRead:
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    row = NoticeService(db).acknowledge_notice(
        organization.id,
        notice_id,
        current_user.id,
        ip=ip,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(row)
    return NoticeAcknowledgementRead.model_validate(row)


@router.get("/{notice_id}/acknowledgements", response_model=NoticeAcknowledgementStatus)
def acknowledgement_status(
    notice_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> NoticeAcknowledgementStatus:
    payload = NoticeService(db).get_acknowledgement_status(organization.id, notice_id)
    return NoticeAcknowledgementStatus.model_validate(payload)
