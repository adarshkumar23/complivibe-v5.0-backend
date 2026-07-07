import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.audit_engagement import AuditEngagement
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.audit_engagement import (
    AuditEngagementCreate,
    AuditEngagementDashboard,
    AuditEngagementRead,
    AuditEngagementScopeImpact,
    AuditEngagementTransitionRequest,
    AuditEngagementUpdate,
)

router = APIRouter(prefix="/compliance/audit-engagements", tags=["audit-engagements"])


def _read(row: AuditEngagement) -> AuditEngagementRead:
    return AuditEngagementRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        audit_type=row.audit_type,
        scope_framework_ids=[uuid.UUID(item) for item in (row.scope_framework_ids or [])],
        assigned_auditor_ids=[uuid.UUID(item) for item in (row.assigned_auditor_ids or [])],
        status=row.status,
        start_date=row.start_date,
        end_date=row.end_date,
        report_issued_at=row.report_issued_at,
        lead_auditor_name=row.lead_auditor_name,
        audit_firm=row.audit_firm,
        notes=row.notes,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=AuditEngagementRead, status_code=status.HTTP_201_CREATED)
def create_engagement(
    payload: AuditEngagementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditEngagementRead:
    row = AuditEngagementService(db).create_engagement(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("", response_model=list[AuditEngagementRead])
def list_engagements(
    status_filter: str | None = Query(default=None, alias="status"),
    audit_type: str | None = Query(default=None),
    framework_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditEngagementRead]:
    rows = AuditEngagementService(db).list_engagements(
        organization.id,
        status_value=status_filter,
        audit_type=audit_type,
        framework_id=framework_id,
        skip=skip,
        limit=limit,
    )
    return [_read(row) for row in rows]


@router.get("/dashboard", response_model=AuditEngagementDashboard)
def engagement_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditEngagementDashboard:
    payload = AuditEngagementService(db).get_engagement_dashboard(organization.id)
    return AuditEngagementDashboard(**payload)


@router.get("/{engagement_id}", response_model=AuditEngagementRead)
def get_engagement(
    engagement_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditEngagementRead:
    row = AuditEngagementService(db).get_engagement(organization.id, engagement_id)
    return _read(row)


@router.get("/{engagement_id}/scope-impact", response_model=AuditEngagementScopeImpact)
def engagement_scope_impact(
    engagement_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditEngagementScopeImpact:
    payload = AuditEngagementService(db).get_scope_impact(organization.id, engagement_id)
    return AuditEngagementScopeImpact(**payload)


@router.patch("/{engagement_id}", response_model=AuditEngagementRead)
def update_engagement(
    engagement_id: uuid.UUID,
    payload: AuditEngagementUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditEngagementRead:
    row = AuditEngagementService(db).update_engagement(organization.id, engagement_id, payload)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{engagement_id}/transition", response_model=AuditEngagementRead)
def transition_engagement_status(
    engagement_id: uuid.UUID,
    payload: AuditEngagementTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditEngagementRead:
    row = AuditEngagementService(db).transition_status(organization.id, engagement_id, payload.new_status, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.delete("/{engagement_id}", response_model=AuditEngagementRead)
def delete_engagement(
    engagement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditEngagementRead:
    row = AuditEngagementService(db).soft_delete_engagement(organization.id, engagement_id, current_user.id)
    db.commit()
    return _read(row)
