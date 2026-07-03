import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.schemas.pbc_audit_findings import (
    PBCBulkCreateRequest,
    PBCBulkCreateResponse,
    PBCRejectRequest,
    PBCRequestResponse,
    PBCSubmitRequest,
)
from app.compliance.services.pbc_request_service import PBCRequestService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance", tags=["pbc_requests_v2"])


def _read(row) -> PBCRequestResponse:
    return PBCRequestResponse(
        id=row.id,
        organization_id=row.organization_id,
        audit_id=row.audit_id,
        item_description=row.item_description,
        assigned_to=row.assigned_to,
        status=row.status,
        due_date=row.due_date,
        evidence_id=row.evidence_id,
        submitted_at=row.submitted_at,
        accepted_at=row.accepted_at,
        rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/audits/{audit_id}/pbc-requests/bulk", response_model=PBCBulkCreateResponse, status_code=status.HTTP_201_CREATED)
def bulk_create_pbc_requests(
    audit_id: uuid.UUID,
    payload: PBCBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PBCBulkCreateResponse:
    rows = PBCRequestService(db).bulk_create(
        organization.id,
        audit_id,
        items=[item.model_dump() for item in payload.items],
        created_by=current_user.id,
    )
    db.commit()
    return PBCBulkCreateResponse(items=[_read(row) for row in rows], count=len(rows))


@router.get("/audits/{audit_id}/pbc-requests", response_model=list[PBCRequestResponse])
def list_pbc_requests_for_audit(
    audit_id: uuid.UUID,
    status_value: str | None = Query(default=None, alias="status"),
    assigned_to: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[PBCRequestResponse]:
    rows = PBCRequestService(db).list_requests(
        organization.id,
        audit_id=audit_id,
        status_value=status_value,
        assigned_to=assigned_to,
        page=page,
        page_size=page_size,
    )
    return [_read(row) for row in rows]


@router.get("/pbc-requests/{request_id}", response_model=PBCRequestResponse)
def get_pbc_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> PBCRequestResponse:
    row = PBCRequestService(db).require_request(organization.id, request_id)
    return _read(row)


@router.post("/pbc-requests/{request_id}/submit", response_model=PBCRequestResponse)
def submit_pbc_request(
    request_id: uuid.UUID,
    payload: PBCSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> PBCRequestResponse:
    row = PBCRequestService(db).submit(
        organization.id,
        request_id,
        submitted_by=current_user.id,
        evidence_id=payload.evidence_id,
    )
    db.commit()
    return _read(row)


@router.post("/pbc-requests/{request_id}/accept", response_model=PBCRequestResponse)
def accept_pbc_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PBCRequestResponse:
    row = PBCRequestService(db).accept(organization.id, request_id, accepted_by=current_user.id)
    db.commit()
    return _read(row)


@router.post("/pbc-requests/{request_id}/reject", response_model=PBCRequestResponse)
def reject_pbc_request(
    request_id: uuid.UUID,
    payload: PBCRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PBCRequestResponse:
    row = PBCRequestService(db).reject(
        organization.id,
        request_id,
        rejected_by=current_user.id,
        rejection_reason=payload.rejection_reason,
    )
    db.commit()
    return _read(row)
