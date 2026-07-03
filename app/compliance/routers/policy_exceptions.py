import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compliance.schemas.attestations_exceptions import (
    PolicyExceptionApproveRequest,
    PolicyExceptionCreateRequest,
    PolicyExceptionResponse,
)
from app.compliance.services.policy_exception_service import PolicyExceptionService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance/policy-exceptions", tags=["policy_exceptions_v2"])


def _read(row) -> PolicyExceptionResponse:
    return PolicyExceptionResponse(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        reason=row.reason,
        requested_by=row.requested_by,
        approved_by=row.approved_by,
        rejected_by=row.rejected_by,
        status=row.status,
        compensating_measure_description=row.compensating_measure_description,
        expiry_date=row.expiry_date,
        approved_at=row.approved_at,
        rejected_at=row.rejected_at,
        expired_at=row.expired_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=PolicyExceptionResponse)
def create_exception(
    payload: PolicyExceptionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyExceptionResponse:
    row = PolicyExceptionService(db).create_exception_v2(
        organization.id,
        policy_id=payload.policy_id,
        reason=payload.reason,
        requested_by=current_user.id,
        compensating_measure_description=payload.compensating_measure_description,
    )
    db.commit()
    return _read(row)


@router.get("", response_model=list[PolicyExceptionResponse])
def list_exceptions(
    policy_id: uuid.UUID | None = None,
    status_value: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[PolicyExceptionResponse]:
    rows = PolicyExceptionService(db).list_exceptions(
        organization.id,
        policy_id=policy_id,
        status_value=status_value,
    )
    start = max((page - 1) * page_size, 0)
    end = start + page_size
    return [_read(r) for r in rows[start:end]]


@router.get("/{exception_id}", response_model=PolicyExceptionResponse)
def get_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> PolicyExceptionResponse:
    row = PolicyExceptionService(db).require_exception(organization.id, exception_id)
    return _read(row)


@router.post("/{exception_id}/approve", response_model=PolicyExceptionResponse)
def approve_exception(
    exception_id: uuid.UUID,
    payload: PolicyExceptionApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyExceptionResponse:
    row = PolicyExceptionService(db).approve_exception_v2(
        organization.id,
        exception_id=exception_id,
        approved_by=current_user.id,
        expiry_date=payload.expiry_date,
    )
    db.commit()
    return _read(row)


@router.post("/{exception_id}/reject", response_model=PolicyExceptionResponse)
def reject_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyExceptionResponse:
    row = PolicyExceptionService(db).reject_exception_v2(
        organization.id,
        exception_id=exception_id,
        rejected_by=current_user.id,
    )
    db.commit()
    return _read(row)
