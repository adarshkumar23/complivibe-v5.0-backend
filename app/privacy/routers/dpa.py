import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.dpa import (
    DPACreate,
    DPALinkActivityRequest,
    DPARead,
    DPASummaryRead,
    DPAStatusTransition,
    DPAUpdate,
)
from app.privacy.services.dpa_service import DPAService

router = APIRouter(prefix="/privacy/dpas", tags=["privacy-dpas"])


@router.post("", response_model=DPARead, status_code=status.HTTP_201_CREATED)
def create_dpa(
    payload: DPACreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPARead:
    row = DPAService(db).create_dpa(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DPARead.model_validate(row)


@router.get("", response_model=list[DPARead])
def list_dpas(
    status_filter: str | None = Query(default=None, alias="status"),
    counterparty_type: str | None = Query(default=None),
    vendor_id: uuid.UUID | None = Query(default=None),
    subprocessor_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[DPARead]:
    rows = DPAService(db).list_dpas(
        organization.id,
        status_filter=status_filter,
        counterparty_type=counterparty_type,
        vendor_id=vendor_id,
        subprocessor_id=subprocessor_id,
    )
    return [DPARead.model_validate(row) for row in rows]


@router.get("/summary", response_model=DPASummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> DPASummaryRead:
    payload = DPAService(db).get_dpa_summary(organization.id)
    return DPASummaryRead.model_validate(payload)


@router.get("/{dpa_id}", response_model=DPARead)
def get_dpa(
    dpa_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> DPARead:
    row = DPAService(db).get_dpa(organization.id, dpa_id)
    return DPARead.model_validate(row)


@router.patch("/{dpa_id}", response_model=DPARead)
def update_dpa(
    dpa_id: uuid.UUID,
    payload: DPAUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPARead:
    row = DPAService(db).update_dpa(organization.id, dpa_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DPARead.model_validate(row)


@router.post("/{dpa_id}/status", response_model=DPARead)
def transition_status(
    dpa_id: uuid.UUID,
    payload: DPAStatusTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPARead:
    row = DPAService(db).transition_status(organization.id, dpa_id, payload.new_status, current_user.id)
    db.commit()
    db.refresh(row)
    return DPARead.model_validate(row)


@router.post("/{dpa_id}/link-activity", response_model=DPARead)
def link_activity(
    dpa_id: uuid.UUID,
    payload: DPALinkActivityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPARead:
    row = DPAService(db).link_processing_activity(organization.id, dpa_id, payload.activity_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DPARead.model_validate(row)


@router.delete("/{dpa_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dpa(
    dpa_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> None:
    DPAService(db).soft_delete_dpa(organization.id, dpa_id, current_user.id)
    db.commit()
    return None
