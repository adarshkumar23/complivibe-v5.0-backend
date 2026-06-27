import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.subprocessor_service import SubprocessorService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.subprocessor import Subprocessor
from app.models.subprocessor_data_transfer import SubprocessorDataTransfer
from app.models.user import User
from app.schemas.subprocessor import (
    SubprocessorCreate,
    SubprocessorDataTransferCreate,
    SubprocessorDataTransferRead,
    SubprocessorDpaStatusUpdate,
    SubprocessorGdprDashboard,
    SubprocessorRead,
    SubprocessorUpdate,
)

router = APIRouter(prefix="/compliance/subprocessors", tags=["subprocessors"])


def _subprocessor_read(row: Subprocessor) -> SubprocessorRead:
    return SubprocessorRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        service_description=row.service_description,
        data_types_processed=row.data_types_processed,
        legal_basis=row.legal_basis,
        geographic_locations=row.geographic_locations,
        data_transfer_mechanism=row.data_transfer_mechanism,
        dpa_status=row.dpa_status,
        dpa_signed_at=row.dpa_signed_at,
        dpa_expiry_date=row.dpa_expiry_date,
        dpa_document_ref=row.dpa_document_ref,
        controller_type=row.controller_type,
        risk_level=row.risk_level,
        status=row.status,
        contact_name=row.contact_name,
        contact_email=row.contact_email,
        review_due_date=row.review_due_date,
        last_reviewed_at=row.last_reviewed_at,
        last_reviewed_by=row.last_reviewed_by,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _transfer_read(row: SubprocessorDataTransfer) -> SubprocessorDataTransferRead:
    return SubprocessorDataTransferRead(
        id=row.id,
        organization_id=row.organization_id,
        subprocessor_id=row.subprocessor_id,
        origin_country=row.origin_country,
        destination_country=row.destination_country,
        data_categories=row.data_categories,
        transfer_mechanism=row.transfer_mechanism,
        legal_basis=row.legal_basis,
        is_active=row.is_active,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.post("", response_model=SubprocessorRead, status_code=status.HTTP_201_CREATED)
def create_subprocessor(
    payload: SubprocessorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> SubprocessorRead:
    row = SubprocessorService(db).create_subprocessor(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _subprocessor_read(row)


@router.get("", response_model=list[SubprocessorRead])
def list_subprocessors(
    status_value: str | None = Query(default=None, alias="status"),
    dpa_status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    controller_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[SubprocessorRead]:
    rows = SubprocessorService(db).list_subprocessors(
        organization.id,
        status_value=status_value,
        dpa_status=dpa_status,
        risk_level=risk_level,
        controller_type=controller_type,
        skip=skip,
        limit=limit,
    )
    return [_subprocessor_read(row) for row in rows]


@router.get("/gdpr-dashboard", response_model=SubprocessorGdprDashboard)
def gdpr_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> SubprocessorGdprDashboard:
    payload = SubprocessorService(db).get_gdpr_dashboard(organization.id)
    return SubprocessorGdprDashboard(**payload)


@router.get("/{subprocessor_id}", response_model=SubprocessorRead)
def get_subprocessor(
    subprocessor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> SubprocessorRead:
    row = SubprocessorService(db).get_subprocessor(organization.id, subprocessor_id)
    return _subprocessor_read(row)


@router.patch("/{subprocessor_id}", response_model=SubprocessorRead)
def update_subprocessor(
    subprocessor_id: uuid.UUID,
    payload: SubprocessorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> SubprocessorRead:
    row = SubprocessorService(db).update_subprocessor(
        organization.id,
        subprocessor_id,
        payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _subprocessor_read(row)


@router.post("/{subprocessor_id}/dpa-status", response_model=SubprocessorRead)
def update_subprocessor_dpa_status(
    subprocessor_id: uuid.UUID,
    payload: SubprocessorDpaStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> SubprocessorRead:
    row = SubprocessorService(db).update_dpa_status(
        organization.id,
        subprocessor_id,
        payload.new_status,
        current_user.id,
        signed_at=payload.signed_at,
        expiry_date=payload.expiry_date,
    )
    db.commit()
    db.refresh(row)
    return _subprocessor_read(row)


@router.post("/{subprocessor_id}/mark-reviewed", response_model=SubprocessorRead)
def mark_subprocessor_reviewed(
    subprocessor_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> SubprocessorRead:
    row = SubprocessorService(db).mark_reviewed(organization.id, subprocessor_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _subprocessor_read(row)


@router.delete("/{subprocessor_id}", response_model=SubprocessorRead)
def delete_subprocessor(
    subprocessor_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> SubprocessorRead:
    row = SubprocessorService(db).soft_delete_subprocessor(organization.id, subprocessor_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _subprocessor_read(row)


@router.post("/{subprocessor_id}/transfers", response_model=SubprocessorDataTransferRead, status_code=status.HTTP_201_CREATED)
def add_subprocessor_transfer(
    subprocessor_id: uuid.UUID,
    payload: SubprocessorDataTransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> SubprocessorDataTransferRead:
    row = SubprocessorService(db).add_data_transfer(
        organization.id,
        subprocessor_id,
        payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _transfer_read(row)


@router.get("/{subprocessor_id}/transfers", response_model=list[SubprocessorDataTransferRead])
def list_subprocessor_transfers(
    subprocessor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[SubprocessorDataTransferRead]:
    rows = SubprocessorService(db).list_data_transfers(organization.id, subprocessor_id)
    return [_transfer_read(row) for row in rows]
