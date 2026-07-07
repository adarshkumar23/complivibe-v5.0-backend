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


def _read(row, context: dict | None = None) -> PBCRequestResponse:
    ctx = context or {}
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
        days_overdue=ctx.get("days_overdue", 0),
        fieldwork_deadline=ctx.get("fieldwork_deadline"),
        overdue_relative_to_fieldwork_deadline=bool(ctx.get("overdue_relative_to_fieldwork_deadline", False)),
        days_past_fieldwork_deadline=ctx.get("days_past_fieldwork_deadline", 0),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _read_one(row, service: PBCRequestService, org_id: uuid.UUID) -> PBCRequestResponse:
    return _read(row, service.build_context(org_id, [row]).get(row.id))


def _read_many(rows: list, service: PBCRequestService, org_id: uuid.UUID) -> list[PBCRequestResponse]:
    context = service.build_context(org_id, rows) if rows else {}
    return [_read(row, context.get(row.id)) for row in rows]


@router.post("/audits/{audit_id}/pbc-requests/bulk", response_model=PBCBulkCreateResponse, status_code=status.HTTP_201_CREATED)
def bulk_create_pbc_requests(
    audit_id: uuid.UUID,
    payload: PBCBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PBCBulkCreateResponse:
    service = PBCRequestService(db)
    rows = service.bulk_create(
        organization.id,
        audit_id,
        items=[item.model_dump() for item in payload.items],
        created_by=current_user.id,
    )
    db.commit()
    return PBCBulkCreateResponse(items=_read_many(rows, service, organization.id), count=len(rows))


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
    service = PBCRequestService(db)
    rows = service.list_requests(
        organization.id,
        audit_id=audit_id,
        status_value=status_value,
        assigned_to=assigned_to,
        page=page,
        page_size=page_size,
    )
    return _read_many(rows, service, organization.id)


@router.get("/pbc-requests/{request_id}", response_model=PBCRequestResponse)
def get_pbc_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> PBCRequestResponse:
    service = PBCRequestService(db)
    row = service.require_request(organization.id, request_id)
    return _read_one(row, service, organization.id)


@router.post("/pbc-requests/{request_id}/submit", response_model=PBCRequestResponse)
def submit_pbc_request(
    request_id: uuid.UUID,
    payload: PBCSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> PBCRequestResponse:
    service = PBCRequestService(db)
    row = service.submit(
        organization.id,
        request_id,
        submitted_by=current_user.id,
        evidence_id=payload.evidence_id,
    )
    db.commit()
    return _read_one(row, service, organization.id)


@router.post("/pbc-requests/{request_id}/accept", response_model=PBCRequestResponse)
def accept_pbc_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PBCRequestResponse:
    service = PBCRequestService(db)
    row = service.accept(organization.id, request_id, accepted_by=current_user.id)
    db.commit()
    return _read_one(row, service, organization.id)


@router.post("/pbc-requests/{request_id}/reject", response_model=PBCRequestResponse)
def reject_pbc_request(
    request_id: uuid.UUID,
    payload: PBCRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PBCRequestResponse:
    service = PBCRequestService(db)
    row = service.reject(
        organization.id,
        request_id,
        rejected_by=current_user.id,
        rejection_reason=payload.rejection_reason,
    )
    db.commit()
    return _read_one(row, service, organization.id)
