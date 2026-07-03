import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.schemas.pbc_audit_findings import (
    AuditFindingCreateRequest,
    AuditFindingRemediationUpdateRequest,
    AuditFindingResponse,
)
from app.compliance.services.audit_finding_service import AuditFindingService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance", tags=["audit_findings_v2"])


def _read(row) -> AuditFindingResponse:
    return AuditFindingResponse(
        id=row.id,
        organization_id=row.organization_id,
        audit_id=row.audit_id,
        control_id=row.control_id,
        title=row.title,
        description=row.description,
        severity=row.severity,
        finding_type=row.finding_type,
        status=row.status,
        remediation_plan=row.remediation_plan,
        remediation_due_date=row.remediation_due_date,
        remediation_owner_id=row.remediation_owner_id,
        linked_risk_id=row.linked_risk_id,
        resolved_at=row.resolved_at,
        closed_at=row.closed_at,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/audits/{audit_id}/findings", response_model=AuditFindingResponse, status_code=status.HTTP_201_CREATED)
def create_audit_finding(
    audit_id: uuid.UUID,
    payload: AuditFindingCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingResponse:
    row = AuditFindingService(db).create_finding_v2(
        organization.id,
        audit_id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        finding_type=payload.finding_type,
        control_id=payload.control_id,
        remediation_plan=payload.remediation_plan,
        remediation_due_date=payload.remediation_due_date,
        remediation_owner_id=payload.remediation_owner_id,
        created_by=current_user.id,
    )
    db.commit()
    return _read(row)


@router.get("/audits/{audit_id}/findings", response_model=list[AuditFindingResponse])
def list_audit_findings(
    audit_id: uuid.UUID,
    severity: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditFindingResponse]:
    rows = AuditFindingService(db).list_findings_v2(
        organization.id,
        audit_id=audit_id,
        severity=severity,
        status_value=status_value,
        page=page,
        page_size=page_size,
    )
    return [_read(row) for row in rows]


@router.get("/audit-findings/summary", response_model=dict)
def get_finding_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> dict:
    return AuditFindingService(db).get_finding_summary(organization.id)


@router.get("/audit-findings/{finding_id}", response_model=AuditFindingResponse)
def get_audit_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditFindingResponse:
    row = AuditFindingService(db).require_finding(organization.id, finding_id)
    return _read(row)


@router.patch("/audit-findings/{finding_id}/remediation", response_model=AuditFindingResponse)
def update_finding_remediation(
    finding_id: uuid.UUID,
    payload: AuditFindingRemediationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingResponse:
    row = AuditFindingService(db).update_remediation(
        organization.id,
        finding_id,
        remediation_plan=payload.remediation_plan,
        remediation_due_date=payload.remediation_due_date,
        remediation_owner_id=payload.remediation_owner_id,
        updated_by=current_user.id,
    )
    db.commit()
    return _read(row)


@router.post("/audit-findings/{finding_id}/resolve", response_model=AuditFindingResponse)
def resolve_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingResponse:
    row = AuditFindingService(db).resolve_finding(organization.id, finding_id, resolved_by=current_user.id)
    db.commit()
    return _read(row)


@router.post("/audit-findings/{finding_id}/accept-risk", response_model=AuditFindingResponse)
def accept_finding_risk(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingResponse:
    row = AuditFindingService(db).accept_risk(organization.id, finding_id, accepted_by=current_user.id)
    db.commit()
    return _read(row)


@router.post("/audit-findings/{finding_id}/close", response_model=AuditFindingResponse)
def close_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingResponse:
    row = AuditFindingService(db).close_finding(organization.id, finding_id, closed_by=current_user.id)
    db.commit()
    return _read(row)
