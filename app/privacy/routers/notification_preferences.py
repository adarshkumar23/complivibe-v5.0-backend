from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.notification_preferences import (
    NotificationPreferenceBulkUpdate,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
)
from app.privacy.services.notification_preference_service import NotificationPreferenceService

router = APIRouter(prefix="/preferences/notifications", tags=["notification-preferences"])


@router.get("", response_model=list[NotificationPreferenceRead])
def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[NotificationPreferenceRead]:
    rows = NotificationPreferenceService(db).get_or_create_preferences(organization.id, current_user.id)
    return [NotificationPreferenceRead.model_validate(row) for row in rows]


@router.put("/bulk", response_model=list[NotificationPreferenceRead])
def bulk_update_notification_preferences(
    payload: NotificationPreferenceBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[NotificationPreferenceRead]:
    rows = NotificationPreferenceService(db).bulk_update_preferences(
        organization.id,
        current_user.id,
        payload.updates,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return [NotificationPreferenceRead.model_validate(row) for row in rows]


@router.put("/{notification_type}", response_model=NotificationPreferenceRead)
def update_notification_preference(
    notification_type: str,
    payload: NotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> NotificationPreferenceRead:
    row = NotificationPreferenceService(db).update_preference(
        organization.id,
        current_user.id,
        notification_type,
        payload.channel,
        payload.is_enabled,
        payload.min_severity,
    )
    db.commit()
    db.refresh(row)
    return NotificationPreferenceRead.model_validate(row)
