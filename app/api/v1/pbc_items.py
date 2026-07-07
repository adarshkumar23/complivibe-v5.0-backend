import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.pbc_service import PbcService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.pbc_item import PbcItem
from app.models.user import User
from app.schemas.pbc_item import (
    PbcItemCreate,
    PbcItemRead,
    PbcItemUpdate,
    PbcRejectRequest,
    PbcSubmitRequest,
    PbcSummary,
)

router = APIRouter(prefix="/compliance/pbc-items", tags=["pbc-items"])


def _read(row: PbcItem, context: dict | None = None) -> PbcItemRead:
    ctx = context or {}
    return PbcItemRead(
        id=row.id,
        organization_id=row.organization_id,
        audit_engagement_id=row.audit_engagement_id,
        title=row.title,
        description=row.description,
        requester_id=row.requester_id,
        assignee_id=row.assignee_id,
        due_date=row.due_date,
        status=row.status,
        evidence_id=row.evidence_id,
        submitted_at=row.submitted_at,
        accepted_at=row.accepted_at,
        rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        days_overdue=ctx.get("days_overdue", 0),
        fieldwork_deadline=ctx.get("fieldwork_deadline"),
        overdue_relative_to_fieldwork_deadline=bool(ctx.get("overdue_relative_to_fieldwork_deadline", False)),
        days_past_fieldwork_deadline=ctx.get("days_past_fieldwork_deadline", 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _read_one(row: PbcItem, service: PbcService, org_id: uuid.UUID) -> PbcItemRead:
    return _read(row, service.build_context(org_id, [row]).get(row.id))


def _read_many(rows: list[PbcItem], service: PbcService, org_id: uuid.UUID) -> list[PbcItemRead]:
    context = service.build_context(org_id, rows) if rows else {}
    return [_read(row, context.get(row.id)) for row in rows]


@router.post("", response_model=PbcItemRead, status_code=status.HTTP_201_CREATED)
def create_pbc_item(
    payload: PbcItemCreate,
    engagement_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.create_pbc_item(organization.id, engagement_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read_one(row, service, organization.id)


@router.get("", response_model=list[PbcItemRead])
def list_pbc_items(
    engagement_id: uuid.UUID | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    overdue_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[PbcItemRead]:
    service = PbcService(db)
    rows = service.list_pbc_items(
        organization.id,
        engagement_id=engagement_id,
        assignee_id=assignee_id,
        status_value=status_filter,
        overdue_only=overdue_only,
        skip=skip,
        limit=limit,
    )
    return _read_many(rows, service, organization.id)


@router.get("/summary", response_model=PbcSummary)
def get_org_pbc_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> PbcSummary:
    payload = PbcService(db).get_pbc_summary(organization.id)
    return PbcSummary(**payload)


@router.get("/{item_id}", response_model=PbcItemRead)
def get_pbc_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.get_pbc_item(organization.id, item_id)
    return _read_one(row, service, organization.id)


@router.patch("/{item_id}", response_model=PbcItemRead)
def update_pbc_item(
    item_id: uuid.UUID,
    payload: PbcItemUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.update_pbc_item(organization.id, item_id, payload)
    db.commit()
    db.refresh(row)
    return _read_one(row, service, organization.id)


@router.post("/{item_id}/submit", response_model=PbcItemRead)
def submit_pbc_item(
    item_id: uuid.UUID,
    payload: PbcSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.submit_pbc_item(
        organization.id,
        item_id,
        current_user.id,
        evidence_id=payload.evidence_id,
    )
    db.commit()
    db.refresh(row)
    return _read_one(row, service, organization.id)


@router.post("/{item_id}/accept", response_model=PbcItemRead)
def accept_pbc_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.accept_pbc_item(organization.id, item_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read_one(row, service, organization.id)


@router.post("/{item_id}/reject", response_model=PbcItemRead)
def reject_pbc_item(
    item_id: uuid.UUID,
    payload: PbcRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.reject_pbc_item(organization.id, item_id, current_user.id, payload.rejection_reason)
    db.commit()
    db.refresh(row)
    return _read_one(row, service, organization.id)


@router.delete("/{item_id}", response_model=PbcItemRead)
def delete_pbc_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> PbcItemRead:
    service = PbcService(db)
    row = service.soft_delete_pbc_item(organization.id, item_id, current_user.id)
    db.commit()
    return _read_one(row, service, organization.id)


@router.get("/engagement/{engagement_id}", response_model=list[PbcItemRead])
def list_pbc_items_for_engagement(
    engagement_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[PbcItemRead]:
    service = PbcService(db)
    rows = service.list_pbc_items(organization.id, engagement_id=engagement_id, skip=skip, limit=limit)
    return _read_many(rows, service, organization.id)


@router.get("/engagement/{engagement_id}/summary", response_model=PbcSummary)
def get_pbc_summary_for_engagement(
    engagement_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> PbcSummary:
    payload = PbcService(db).get_pbc_summary(organization.id, engagement_id)
    return PbcSummary(**payload)
