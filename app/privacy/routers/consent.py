import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.consent import (
    ConsentInboundEvent,
    ConsentRecordCreate,
    ConsentRecordRead,
    ConsentStatusRead,
    ConsentSummaryRead,
    ConsentWithdrawRequest,
    GoogleConsentModeV2Create,
    GoogleConsentModeV2Read,
    GoogleConsentModeV2StatusRead,
)
from app.privacy.services.consent_service import ConsentService

router = APIRouter(prefix="/privacy/consent", tags=["privacy-consent"])


@router.post("/events", response_model=ConsentRecordRead, status_code=status.HTTP_201_CREATED)
def receive_consent_event(
    payload: ConsentInboundEvent,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> ConsentRecordRead:
    row = ConsentService(db).receive_inbound_event(x_complivibe_key or "", payload)
    db.commit()
    db.refresh(row)
    return ConsentRecordRead.model_validate(row)


@router.post("", response_model=ConsentRecordRead, status_code=status.HTTP_201_CREATED)
def record_consent(
    payload: ConsentRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> ConsentRecordRead:
    row = ConsentService(db).record_consent(
        organization.id,
        payload.processing_activity_id,
        payload,
        granted=payload.granted,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ConsentRecordRead.model_validate(row)


@router.get("", response_model=list[ConsentRecordRead])
def list_consents(
    activity_id: uuid.UUID | None = Query(default=None),
    granted: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[ConsentRecordRead]:
    rows = ConsentService(db).list_consents(
        organization.id,
        activity_id=activity_id,
        granted=granted,
        skip=skip,
        limit=limit,
    )
    return [ConsentRecordRead.model_validate(row) for row in rows]


@router.get("/summary", response_model=ConsentSummaryRead)
def consent_summary(
    activity_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> ConsentSummaryRead:
    payload = ConsentService(db).get_consent_summary(organization.id, activity_id=activity_id)
    return ConsentSummaryRead.model_validate(payload)


@router.post("/google-consent-mode-v2", response_model=GoogleConsentModeV2Read, status_code=status.HTTP_201_CREATED)
def record_google_consent_mode_v2(
    payload: GoogleConsentModeV2Create,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> GoogleConsentModeV2Read:
    row = ConsentService(db).record_google_consent_mode_v2(
        organization.id,
        payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return GoogleConsentModeV2Read.model_validate(row)


@router.get("/google-consent-mode-v2", response_model=list[GoogleConsentModeV2Read])
def list_google_consent_mode_v2(
    domain: str | None = Query(default=None),
    subject_identifier: str | None = Query(default=None, min_length=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[GoogleConsentModeV2Read]:
    rows = ConsentService(db).list_google_consent_mode_v2_events(
        organization.id,
        domain=domain,
        subject_identifier=subject_identifier,
        skip=skip,
        limit=limit,
    )
    return [GoogleConsentModeV2Read.model_validate(row) for row in rows]


@router.get("/google-consent-mode-v2/status", response_model=GoogleConsentModeV2StatusRead)
def google_consent_mode_v2_status(
    domain: str = Query(..., min_length=1),
    subject_identifier: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> GoogleConsentModeV2StatusRead:
    payload = ConsentService(db).get_google_consent_mode_v2_status(
        organization.id,
        domain,
        subject_identifier,
    )
    return GoogleConsentModeV2StatusRead.model_validate(payload)


@router.post("/{consent_id}/withdraw", response_model=ConsentRecordRead)
def withdraw_consent(
    consent_id: uuid.UUID,
    payload: ConsentWithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> ConsentRecordRead:
    row = ConsentService(db).withdraw_consent(
        organization.id,
        consent_id,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ConsentRecordRead.model_validate(row)


@router.get("/status", response_model=ConsentStatusRead)
def consent_status(
    activity_id: uuid.UUID = Query(...),
    subject_identifier: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> ConsentStatusRead:
    payload = ConsentService(db).get_consent_status(
        organization.id,
        activity_id,
        subject_identifier,
    )
    return ConsentStatusRead.model_validate(payload)
