import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.policy_exception_service import PolicyExceptionService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.policy_exception import PolicyException
from app.models.policy_exception_approval import PolicyExceptionApproval
from app.models.user import User
from app.schemas.policy_exception import (
    PolicyExceptionApprovalCreate,
    PolicyExceptionApprovalResponse,
    PolicyExceptionCreate,
    PolicyExceptionDashboardResponse,
    PolicyExceptionRejectionCreate,
    PolicyExceptionResponse,
    PolicyExceptionSummaryResponse,
    PolicyExceptionUpdate,
    PolicyRef,
)

router = APIRouter(prefix="/compliance", tags=["policy-exceptions"])


def _read_approval(row: PolicyExceptionApproval) -> PolicyExceptionApprovalResponse:
    return PolicyExceptionApprovalResponse(
        id=row.id,
        exception_id=row.exception_id,
        reviewed_by=row.reviewed_by,
        decision=row.decision,
        decision_reason=row.decision_reason,
        approved_expiry_date=row.approved_expiry_date,
        conditions=row.conditions,
        reviewed_at=row.reviewed_at,
    )


def _read_exception(
    service: PolicyExceptionService,
    row: PolicyException,
    *,
    approval: PolicyExceptionApproval | None = None,
    policy: CompliancePolicy | None = None,
) -> PolicyExceptionResponse:
    policy_row = policy or service.require_policy_in_org(row.organization_id, row.policy_id)
    approval_row = approval if approval is not None else service.get_approval(row.organization_id, row.id)
    return PolicyExceptionResponse(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        policy_version=row.policy_version,
        title=row.title,
        description=row.description,
        justification=row.justification,
        compensating_measure=row.compensating_measure,
        requestor_scope=row.requestor_scope,
        requested_by=row.requested_by,
        requested_expiry_date=row.requested_expiry_date,
        status=row.status,
        approved_expiry_date=row.approved_expiry_date,
        risk_level=row.risk_level,
        created_at=row.created_at,
        updated_at=row.updated_at,
        approval=_read_approval(approval_row) if approval_row else None,
        policy=PolicyRef(id=policy_row.id, name=policy_row.title),
    )


@router.post("/policy-exceptions", response_model=PolicyExceptionResponse, status_code=status.HTTP_201_CREATED)
def create_policy_exception(
    payload: PolicyExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_exceptions:submit")),
) -> PolicyExceptionResponse:
    service = PolicyExceptionService(db)
    row = service.create_exception(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read_exception(service, row)


@router.get("/policy-exceptions/dashboard", response_model=PolicyExceptionDashboardResponse)
def policy_exception_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_exceptions:view")),
) -> PolicyExceptionDashboardResponse:
    service = PolicyExceptionService(db)
    payload = service.get_org_exception_dashboard(organization.id)
    return PolicyExceptionDashboardResponse(
        total_pending=payload["total_pending"],
        total_active=payload["total_active"],
        expiring_soon=[_read_exception(service, row) for row in payload["expiring_soon"]],
        high_risk_active=[_read_exception(service, row) for row in payload["high_risk_active"]],
        overdue_pending=[_read_exception(service, row) for row in payload["overdue_pending"]],
    )


@router.get("/policy-exceptions", response_model=list[PolicyExceptionResponse])
def list_policy_exceptions(
    policy_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    requested_by: uuid.UUID | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_exceptions:view")),
) -> list[PolicyExceptionResponse]:
    service = PolicyExceptionService(db)
    rows = service.list_exceptions(
        organization.id,
        policy_id=policy_id,
        status_value=status_filter,
        requested_by=requested_by,
        risk_level=risk_level,
    )
    return [_read_exception(service, row) for row in rows]


@router.patch("/policy-exceptions/{exception_id}", response_model=PolicyExceptionResponse)
def update_policy_exception(
    exception_id: uuid.UUID,
    payload: PolicyExceptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_exceptions:submit")),
) -> PolicyExceptionResponse:
    service = PolicyExceptionService(db)
    row = service.update_exception(organization.id, exception_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read_exception(service, row)


@router.delete("/policy-exceptions/{exception_id}", response_model=PolicyExceptionResponse)
def withdraw_policy_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_exceptions:submit")),
) -> PolicyExceptionResponse:
    service = PolicyExceptionService(db)
    row = service.withdraw_exception(organization.id, exception_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read_exception(service, row)


@router.get("/policies/{policy_id}/exception-summary", response_model=PolicyExceptionSummaryResponse)
def policy_exception_summary(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_exceptions:view")),
) -> PolicyExceptionSummaryResponse:
    payload = PolicyExceptionService(db).get_policy_exception_summary(organization.id, policy_id)
    return PolicyExceptionSummaryResponse(**payload)
