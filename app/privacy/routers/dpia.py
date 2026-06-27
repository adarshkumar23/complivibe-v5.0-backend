import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.dpia import (
    DPIAApproveRequest,
    DPIAChecklistRespondRequest,
    DPIACreate,
    DPIARead,
    DPIARejectRequest,
    DPIASubmitForReviewRequest,
    DPIASummaryRead,
    DPIAUpdate,
)
from app.privacy.services.dpia_service import DPIAService

router = APIRouter(prefix="/privacy/dpias", tags=["privacy-dpias"])


@router.post("", response_model=DPIARead, status_code=status.HTTP_201_CREATED)
def create_dpia(
    payload: DPIACreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPIARead:
    service = DPIAService(db)
    row = service.create_dpia(organization.id, payload.processing_activity_id, payload, current_user.id)
    db.commit()
    return DPIARead.model_validate(service.get_dpia(organization.id, row.id))


@router.get("", response_model=list[DPIARead])
def list_dpias(
    status_filter: str | None = Query(default=None, alias="status"),
    processing_activity_id: uuid.UUID | None = Query(default=None),
    residual_risk_level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[DPIARead]:
    service = DPIAService(db)
    rows = service.list_dpias(
        organization.id,
        status_filter=status_filter,
        processing_activity_id=processing_activity_id,
        residual_risk_level=residual_risk_level,
    )
    return [DPIARead.model_validate(service.get_dpia(organization.id, row.id)) for row in rows]


@router.get("/summary", response_model=DPIASummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> DPIASummaryRead:
    payload = DPIAService(db).get_dpia_summary(organization.id)
    return DPIASummaryRead.model_validate(payload)


@router.get("/{dpia_id}", response_model=DPIARead)
def get_dpia(
    dpia_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> DPIARead:
    row = DPIAService(db).get_dpia(organization.id, dpia_id)
    return DPIARead.model_validate(row)


@router.patch("/{dpia_id}", response_model=DPIARead)
def update_dpia(
    dpia_id: uuid.UUID,
    payload: DPIAUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPIARead:
    service = DPIAService(db)
    row = service.update_dpia(organization.id, dpia_id, payload, current_user.id)
    db.commit()
    return DPIARead.model_validate(service.get_dpia(organization.id, row.id))


@router.post("/{dpia_id}/checklist", response_model=DPIARead)
def respond_checklist(
    dpia_id: uuid.UUID,
    payload: DPIAChecklistRespondRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPIARead:
    service = DPIAService(db)
    row = service.respond_checklist(organization.id, dpia_id, [item.model_dump() for item in payload.responses], current_user.id)
    db.commit()
    return DPIARead.model_validate(service.get_dpia(organization.id, row.id))


@router.post("/{dpia_id}/submit-for-review", response_model=DPIARead)
def submit_for_review(
    dpia_id: uuid.UUID,
    payload: DPIASubmitForReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DPIARead:
    service = DPIAService(db)
    row = service.submit_for_review(organization.id, dpia_id, payload.reviewer_id, current_user.id)
    db.commit()
    return DPIARead.model_validate(service.get_dpia(organization.id, row.id))


@router.post("/{dpia_id}/approve", response_model=DPIARead)
def approve_dpia(
    dpia_id: uuid.UUID,
    payload: DPIAApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:approve")),
) -> DPIARead:
    service = DPIAService(db)
    row = service.approve_dpia(organization.id, dpia_id, current_user.id, notes=payload.notes)
    db.commit()
    return DPIARead.model_validate(service.get_dpia(organization.id, row.id))


@router.post("/{dpia_id}/reject", response_model=DPIARead)
def reject_dpia(
    dpia_id: uuid.UUID,
    payload: DPIARejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:approve")),
) -> DPIARead:
    service = DPIAService(db)
    row = service.reject_dpia(organization.id, dpia_id, current_user.id, payload.notes)
    db.commit()
    return DPIARead.model_validate(service.get_dpia(organization.id, row.id))


@router.delete("/{dpia_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dpia(
    dpia_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> None:
    DPIAService(db).soft_delete_dpia(organization.id, dpia_id, current_user.id)
    db.commit()
    return None
