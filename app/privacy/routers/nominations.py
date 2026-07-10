import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.nomination import NominationCreate, NominationRead, NominationRevokeRequest
from app.privacy.services.nomination_service import NominationService

router = APIRouter(prefix="/privacy/nominations", tags=["privacy-nominations"])


@router.post("", response_model=NominationRead, status_code=status.HTTP_201_CREATED)
def create_nomination(
    payload: NominationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> NominationRead:
    row = NominationService(db).create_nomination(
        organization.id,
        subject_identifier=payload.subject_identifier,
        activation_trigger=payload.activation_trigger,
        nominee_name=payload.nominee_name,
        nominee_contact=payload.nominee_contact,
        nominee_user_id=payload.nominee_user_id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return NominationRead.model_validate(row)


@router.get("/active", response_model=NominationRead | None)
def get_active_nomination(
    subject_identifier: str = Query(...),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> NominationRead | None:
    row = NominationService(db).get_active_nomination(organization.id, subject_identifier)
    if row is None:
        return None
    return NominationRead.model_validate(row)


@router.post("/{nomination_id}/activate", response_model=NominationRead)
def activate_nomination(
    nomination_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> NominationRead:
    row = NominationService(db).activate_nomination(organization.id, nomination_id, actor_user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return NominationRead.model_validate(row)


@router.post("/{nomination_id}/revoke", response_model=NominationRead)
def revoke_nomination(
    nomination_id: uuid.UUID,
    payload: NominationRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> NominationRead:
    row = NominationService(db).revoke_nomination(
        organization.id, nomination_id, reason=payload.reason, actor_user_id=current_user.id
    )
    db.commit()
    db.refresh(row)
    return NominationRead.model_validate(row)
