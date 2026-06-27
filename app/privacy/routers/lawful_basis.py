import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.lawful_basis import (
    LawfulBasisCreate,
    LawfulBasisRead,
    LawfulBasisSummaryRead,
    LawfulBasisUpdate,
)
from app.privacy.services.lawful_basis_service import LawfulBasisService

router = APIRouter(prefix="/privacy/lawful-basis", tags=["privacy-lawful-basis"])


@router.post("", response_model=LawfulBasisRead, status_code=status.HTTP_201_CREATED)
def document_basis(
    payload: LawfulBasisCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> LawfulBasisRead:
    row = LawfulBasisService(db).document_basis(organization.id, payload.processing_activity_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return LawfulBasisRead.model_validate(row)


@router.get("", response_model=list[LawfulBasisRead])
def list_all(
    lawful_basis: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[LawfulBasisRead]:
    rows = LawfulBasisService(db).list_all_bases(organization.id, lawful_basis=lawful_basis, is_active=is_active)
    return [LawfulBasisRead.model_validate(row) for row in rows]


@router.get("/summary", response_model=LawfulBasisSummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> LawfulBasisSummaryRead:
    payload = LawfulBasisService(db).get_basis_summary(organization.id)
    return LawfulBasisSummaryRead.model_validate(payload)


@router.get("/activity/{activity_id}", response_model=list[LawfulBasisRead])
def get_activity_records(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[LawfulBasisRead]:
    rows = LawfulBasisService(db).get_basis_records(organization.id, activity_id)
    return [LawfulBasisRead.model_validate(row) for row in rows]


@router.patch("/{record_id}", response_model=LawfulBasisRead)
def update_basis(
    record_id: uuid.UUID,
    payload: LawfulBasisUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> LawfulBasisRead:
    row = LawfulBasisService(db).update_basis(organization.id, record_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return LawfulBasisRead.model_validate(row)


@router.post("/{record_id}/deactivate", response_model=LawfulBasisRead)
def deactivate_basis(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> LawfulBasisRead:
    row = LawfulBasisService(db).deactivate_basis(organization.id, record_id, current_user.id)
    db.commit()
    db.refresh(row)
    return LawfulBasisRead.model_validate(row)
