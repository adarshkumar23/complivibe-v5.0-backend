import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.control_exception_service import ControlExceptionService
from app.core.deps import (
    get_current_active_user,
    get_current_organization,
    get_db,
    require_org_membership,
    require_permission,
)
from app.models.control_exception import ControlException
from app.models.control_exception_approval import ControlExceptionApproval
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.control_exception import (
    ControlExceptionApproveRequest,
    ControlExceptionCreate,
    ControlExceptionDetail,
    ControlExceptionExpiryCheckResponse,
    ControlExceptionRead,
    ControlExceptionRejectRequest,
    ControlExceptionRevokeRequest,
    ControlExceptionSummary,
)

router = APIRouter(prefix="/compliance/control-exceptions", tags=["control-exceptions"])


def _read_exception(row: ControlException) -> ControlExceptionRead:
    return ControlExceptionRead(
        id=row.id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        title=row.title,
        description=row.description,
        exception_type=row.exception_type,
        risk_acceptance_reason=row.risk_acceptance_reason,
        compensating_control_id=row.compensating_control_id,
        compensating_description=row.compensating_description,
        requested_by_user_id=row.requested_by_user_id,
        owner_user_id=row.owner_user_id,
        status=row.status,
        approved_by_user_id=row.approved_by_user_id,
        approved_at=row.approved_at,
        rejected_by_user_id=row.rejected_by_user_id,
        rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        revoked_by_user_id=row.revoked_by_user_id,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,
        effective_date=row.effective_date,
        expiry_date=row.expiry_date,
        review_date=row.review_date,
        auto_expired_at=row.auto_expired_at,
        tags_json=row.tags_json,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
        review_overdue=(
            row.status == "active"
            and row.review_date is not None
            and row.review_date < ControlExceptionService.utcdate()
        ),
    )


def _read_approval_step(row: ControlExceptionApproval) -> dict:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "exception_id": row.exception_id,
        "approver_user_id": row.approver_user_id,
        "sequence": row.sequence,
        "status": row.status,
        "decision_notes": row.decision_notes,
        "decided_at": row.decided_at,
        "created_at": row.created_at,
    }


@router.post("", response_model=ControlExceptionRead, status_code=status.HTTP_201_CREATED)
def create_control_exception(
    payload: ControlExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlExceptionRead:
    service = ControlExceptionService(db)
    row = service.create_exception(
        payload,
        organization.id,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _read_exception(row)


@router.get("/summary", response_model=ControlExceptionSummary)
def control_exception_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlExceptionSummary:
    return ControlExceptionSummary(**ControlExceptionService(db).summary(organization.id))


@router.get("", response_model=list[ControlExceptionRead])
def list_control_exceptions(
    status_filter: str | None = Query(default=None, alias="status"),
    control_id: uuid.UUID | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    exception_type: str | None = Query(default=None),
    include_expired: bool = Query(default=False),
    expiring_within_days: int | None = Query(default=None, ge=0, le=3650),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[ControlExceptionRead]:
    rows = ControlExceptionService(db).list_exceptions(
        org_id=organization.id,
        status_filter=status_filter,
        control_id=control_id,
        owner_user_id=owner_user_id,
        exception_type=exception_type,
        include_expired=include_expired,
        expiring_within_days=expiring_within_days,
    )
    return [_read_exception(row) for row in rows]


@router.post("/check-expiry", response_model=ControlExceptionExpiryCheckResponse)
def check_control_exception_expiry(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlExceptionExpiryCheckResponse:
    service = ControlExceptionService(db)
    started_at = service.utcnow()
    expired_count = service.check_and_expire(organization.id)

    expired_rows = db.execute(
        select(ControlException)
        .where(
            ControlException.organization_id == organization.id,
            ControlException.status == "expired",
            ControlException.auto_expired_at.is_not(None),
            ControlException.auto_expired_at >= started_at,
        )
        .order_by(ControlException.auto_expired_at.desc())
    ).scalars().all()

    db.commit()
    return ControlExceptionExpiryCheckResponse(
        expired_count=expired_count,
        expired_exceptions=[_read_exception(row) for row in expired_rows],
    )


@router.get("/{exception_id}", response_model=ControlExceptionDetail)
def get_control_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlExceptionDetail:
    service = ControlExceptionService(db)
    row = service.require_exception_in_org(organization.id, exception_id)
    approvals = service.approval_steps(organization.id, exception_id)
    return ControlExceptionDetail(**_read_exception(row).model_dump(), approvals=[_read_approval_step(step) for step in approvals])


@router.post("/{exception_id}/approve", response_model=ControlExceptionRead)
def approve_control_exception(
    exception_id: uuid.UUID,
    payload: ControlExceptionApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    # The endpoint gate is org membership, NOT exceptions:approve. Authority to
    # approve is decided per approval step inside the service: an assigned approver
    # may clear their own step, and exceptions:override is the break-glass. Keeping
    # exceptions:approve here would collapse override back into the endpoint gate.
    _: Membership = Depends(require_org_membership),
) -> ControlExceptionRead:
    row = ControlExceptionService(db).approve(
        exception_id=exception_id,
        approver_user_id=current_user.id,
        decision_notes=payload.decision_notes,
        org_id=organization.id,
    )
    db.commit()
    db.refresh(row)
    return _read_exception(row)


@router.post("/{exception_id}/reject", response_model=ControlExceptionRead)
def reject_control_exception(
    exception_id: uuid.UUID,
    payload: ControlExceptionRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("exceptions:approve")),
) -> ControlExceptionRead:
    row = ControlExceptionService(db).reject(
        exception_id=exception_id,
        rejector_user_id=current_user.id,
        rejection_reason=payload.rejection_reason,
        org_id=organization.id,
    )
    db.commit()
    db.refresh(row)
    return _read_exception(row)


@router.post("/{exception_id}/revoke", response_model=ControlExceptionRead)
def revoke_control_exception(
    exception_id: uuid.UUID,
    payload: ControlExceptionRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlExceptionRead:
    row = ControlExceptionService(db).revoke(
        exception_id=exception_id,
        revoker_user_id=current_user.id,
        revocation_reason=payload.revocation_reason,
        org_id=organization.id,
    )
    db.commit()
    db.refresh(row)
    return _read_exception(row)
