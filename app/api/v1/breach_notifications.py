import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.breach_notification_service import BreachNotificationService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.breach_notification import (
    BreachGenerateArticle33DraftRead,
    BreachNotificationCreate,
    BreachNotificationRead,
    BreachPrivacyFieldsUpdate,
    BreachRecordArticle33SentRequest,
    BreachRecordSubjectsNotifiedRequest,
)

router = APIRouter(prefix="/compliance/breach-notifications", tags=["breach-notifications"])


def _read(service: BreachNotificationService, row) -> BreachNotificationRead:
    return BreachNotificationRead.model_validate(service.breach_response_payload(row))


@router.post("", response_model=BreachNotificationRead, status_code=status.HTTP_201_CREATED)
def create_breach_notification(
    issue_id: uuid.UUID = Query(...),
    payload: BreachNotificationCreate = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.create_breach_notification(organization.id, issue_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.get("", response_model=list[BreachNotificationRead])
def list_breaches(
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[BreachNotificationRead]:
    service = BreachNotificationService(db)
    rows = service.list_breach_notifications(organization.id, status_value=status_value)
    return [_read(service, row) for row in rows]


@router.get("/{breach_id}", response_model=BreachNotificationRead)
def get_breach(
    breach_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.get_breach_notification(organization.id, breach_id)
    return _read(service, row)


@router.post("/{breach_id}/record-regulator-notification", response_model=BreachNotificationRead)
def record_regulator_notification(
    breach_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.record_regulator_notification(organization.id, breach_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.post("/{breach_id}/record-subject-notification", response_model=BreachNotificationRead)
def record_subject_notification(
    breach_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.record_subject_notification(organization.id, breach_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.post("/{breach_id}/close", response_model=BreachNotificationRead)
def close_breach(
    breach_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.close_breach(organization.id, breach_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.patch("/{breach_id}/privacy-fields", response_model=BreachNotificationRead)
def update_privacy_fields(
    breach_id: uuid.UUID,
    payload: BreachPrivacyFieldsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.update_privacy_fields(organization.id, breach_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.post("/{breach_id}/generate-article33-draft", response_model=BreachGenerateArticle33DraftRead)
def generate_article33_draft(
    breach_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachGenerateArticle33DraftRead:
    payload = BreachNotificationService(db).generate_article33_draft(organization.id, breach_id, current_user.id, db)
    db.commit()
    return BreachGenerateArticle33DraftRead.model_validate(payload)


@router.post("/{breach_id}/record-article33-sent", response_model=BreachNotificationRead)
def record_article33_sent(
    breach_id: uuid.UUID,
    payload: BreachRecordArticle33SentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.record_article33_sent(
        organization.id,
        breach_id,
        current_user.id,
        sent_to=payload.sent_to,
    )
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.post("/{breach_id}/record-subjects-notified", response_model=BreachNotificationRead)
def record_subjects_notified_privacy(
    breach_id: uuid.UUID,
    payload: BreachRecordSubjectsNotifiedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> BreachNotificationRead:
    service = BreachNotificationService(db)
    row = service.record_subjects_notified_privacy(
        organization.id,
        breach_id,
        current_user.id,
        count=payload.count,
    )
    db.commit()
    db.refresh(row)
    return _read(service, row)
