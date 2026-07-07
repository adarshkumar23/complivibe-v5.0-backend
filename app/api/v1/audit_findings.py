import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.audit_finding_service import AuditFindingService
from app.compliance.services.issue_service import IssueService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.audit_finding import AuditFinding
from app.models.issue import Issue
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.audit_finding import (
    AuditFindingBulkTransitionRequest,
    AuditFindingBulkTransitionResponse,
    AuditFindingCreate,
    AuditFindingLinkRiskRequest,
    AuditFindingRead,
    AuditFindingSummary,
    AuditFindingTransitionRequest,
    AuditFindingUpdate,
)
from app.schemas.issue import IssuePromoteCreate, IssueRead

router = APIRouter(prefix="/compliance/audit-findings", tags=["audit-findings"])


def _read(row: AuditFinding, context: dict | None = None) -> AuditFindingRead:
    ctx = context or {}
    return AuditFindingRead(
        id=row.id,
        organization_id=row.organization_id,
        audit_engagement_id=row.audit_engagement_id,
        finding_ref=row.finding_ref,
        severity=row.severity,
        framework_ref=row.framework_ref,
        title=row.title,
        description=row.description,
        assigned_owner_id=row.assigned_owner_id,
        remediation_action=row.remediation_action,
        target_remediation_date=row.target_remediation_date,
        status=row.status,
        risk_register_entry_id=row.risk_register_entry_id,
        control_id=row.control_id,
        control_name=ctx.get("control_name"),
        control_status=ctx.get("control_status"),
        control_archived=bool(ctx.get("control_archived", False)),
        scope_changed_since_creation=bool(ctx.get("scope_changed_since_creation", False)),
        closed_at=row.closed_at,
        closed_by=row.closed_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _read_many(rows: list[AuditFinding], service: AuditFindingService) -> list[AuditFindingRead]:
    context = service.build_context(rows[0].organization_id, rows) if rows else {}
    return [_read(row, context.get(row.id)) for row in rows]


def _issue_read(row: Issue) -> IssueRead:
    return IssueRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        description=row.description,
        issue_type=row.issue_type,
        severity=row.severity,
        source_type=row.source_type,
        source_id=row.source_id,
        status=row.status,
        owner_id=row.owner_id,
        assigned_to=row.assigned_to,
        created_by=row.created_by,
        resolution_note=row.resolution_note,
        resolved_at=row.resolved_at,
        closed_at=row.closed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


@router.post("", response_model=AuditFindingRead, status_code=status.HTTP_201_CREATED)
def create_finding(
    payload: AuditFindingCreate,
    engagement_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingRead:
    service = AuditFindingService(db)
    row = service.create_finding(organization.id, engagement_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row, service.build_context(organization.id, [row]).get(row.id))


@router.get("", response_model=list[AuditFindingRead])
def list_findings(
    engagement_id: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_owner_id: uuid.UUID | None = Query(default=None),
    framework_ref: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditFindingRead]:
    service = AuditFindingService(db)
    rows = service.list_findings(
        organization.id,
        engagement_id=engagement_id,
        severity=severity,
        status_value=status_filter,
        assigned_owner_id=assigned_owner_id,
        framework_ref=framework_ref,
        skip=skip,
        limit=limit,
    )
    return _read_many(rows, service)


@router.get("/engagement/{engagement_id}", response_model=list[AuditFindingRead])
def list_findings_for_engagement(
    engagement_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditFindingRead]:
    service = AuditFindingService(db)
    rows = service.list_findings(organization.id, engagement_id=engagement_id, skip=skip, limit=limit)
    return _read_many(rows, service)


@router.get("/engagement/{engagement_id}/summary", response_model=AuditFindingSummary)
def finding_summary_for_engagement(
    engagement_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditFindingSummary:
    payload = AuditFindingService(db).get_finding_summary(organization.id, engagement_id=engagement_id)
    return AuditFindingSummary(**payload)


@router.post("/{finding_id}/create-issue", response_model=IssueRead, status_code=status.HTTP_201_CREATED)
def create_issue_from_finding(
    finding_id: uuid.UUID,
    payload: IssuePromoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueRead:
    row = IssueService(db).promote_from_finding(organization.id, finding_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _issue_read(row)


@router.patch("/{finding_id}", response_model=AuditFindingRead)
def update_finding(
    finding_id: uuid.UUID,
    payload: AuditFindingUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingRead:
    service = AuditFindingService(db)
    row = service.update_finding(organization.id, finding_id, payload)
    db.commit()
    db.refresh(row)
    return _read(row, service.build_context(organization.id, [row]).get(row.id))


@router.post("/{finding_id}/transition", response_model=AuditFindingRead)
def transition_finding_status(
    finding_id: uuid.UUID,
    payload: AuditFindingTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingRead:
    service = AuditFindingService(db)
    row = service.transition_status(organization.id, finding_id, payload.new_status, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row, service.build_context(organization.id, [row]).get(row.id))


@router.post("/{finding_id}/link-risk", response_model=AuditFindingRead)
def link_finding_to_risk(
    finding_id: uuid.UUID,
    payload: AuditFindingLinkRiskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingRead:
    service = AuditFindingService(db)
    row = service.link_to_risk(organization.id, finding_id, payload.risk_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row, service.build_context(organization.id, [row]).get(row.id))


@router.post("/bulk-transition", response_model=AuditFindingBulkTransitionResponse)
def bulk_transition_findings(
    payload: AuditFindingBulkTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingBulkTransitionResponse:
    response = AuditFindingService(db).bulk_transition(organization.id, payload.finding_ids, payload.new_status, current_user.id)
    db.commit()
    return AuditFindingBulkTransitionResponse(**response)


@router.delete("/{finding_id}", response_model=AuditFindingRead)
def delete_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditFindingRead:
    service = AuditFindingService(db)
    row = service.soft_delete_finding(organization.id, finding_id, current_user.id)
    db.commit()
    return _read(row, service.build_context(organization.id, [row]).get(row.id))
