import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.audit_schedule_service import AuditScheduleService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.audit_engagement import AuditEngagement
from app.models.audit_schedule import AuditSchedule
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.schemas.audit_engagement import AuditEngagementRead
from app.schemas.audit_schedule import (
    AuditScheduleCreate,
    AuditScheduleLinkEngagementRequest,
    AuditScheduleRead,
    AuditScheduleReminderSweepResult,
    AuditScheduleStatusRequest,
    AuditScheduleUpdate,
)

router = APIRouter(prefix="/compliance/audit-schedules", tags=["audit-schedules"])


def _schedule_read(row: AuditSchedule) -> AuditScheduleRead:
    return AuditScheduleRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        audit_type=row.audit_type,
        framework_id=row.framework_id,
        recurrence_pattern=row.recurrence_pattern,
        next_audit_date=row.next_audit_date,
        preparation_reminder_days=row.preparation_reminder_days,
        last_reminder_sent_at=row.last_reminder_sent_at,
        last_audit_engagement_id=row.last_audit_engagement_id,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _engagement_read(row: AuditEngagement) -> AuditEngagementRead:
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


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


@router.post("", response_model=AuditScheduleRead, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: AuditScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditScheduleRead:
    row = AuditScheduleService(db).create_schedule(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _schedule_read(row)


@router.get("", response_model=list[AuditScheduleRead])
def list_schedules(
    status_filter: str | None = Query(default=None, alias="status"),
    framework_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditScheduleRead]:
    rows = AuditScheduleService(db).list_schedules(
        organization.id,
        status_value=status_filter,
        framework_id=framework_id,
        skip=skip,
        limit=limit,
    )
    return [_schedule_read(row) for row in rows]


@router.post("/trigger-reminder-sweep", response_model=AuditScheduleReminderSweepResult)
def trigger_schedule_reminder_sweep(
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("audit:write")),
    _: Organization = Depends(get_current_organization),
) -> AuditScheduleReminderSweepResult:
    _require_org_admin(db, membership)
    result = AuditScheduleService(db).process_schedule_reminders()
    db.commit()
    return AuditScheduleReminderSweepResult(**result)


@router.get("/{schedule_id}", response_model=AuditScheduleRead)
def get_schedule(
    schedule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditScheduleRead:
    row = AuditScheduleService(db).get_schedule(organization.id, schedule_id)
    return _schedule_read(row)


@router.patch("/{schedule_id}", response_model=AuditScheduleRead)
def update_schedule(
    schedule_id: uuid.UUID,
    payload: AuditScheduleUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditScheduleRead:
    row = AuditScheduleService(db).update_schedule(organization.id, schedule_id, payload)
    db.commit()
    db.refresh(row)
    return _schedule_read(row)


@router.post("/{schedule_id}/status", response_model=AuditScheduleRead)
def set_schedule_status(
    schedule_id: uuid.UUID,
    payload: AuditScheduleStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditScheduleRead:
    row = AuditScheduleService(db).set_schedule_status(organization.id, schedule_id, payload.new_status, current_user.id)
    db.commit()
    db.refresh(row)
    return _schedule_read(row)


@router.post("/{schedule_id}/link-engagement", response_model=AuditScheduleRead)
def link_schedule_engagement(
    schedule_id: uuid.UUID,
    payload: AuditScheduleLinkEngagementRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditScheduleRead:
    row = AuditScheduleService(db).link_engagement(organization.id, schedule_id, payload.engagement_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _schedule_read(row)


@router.delete("/{schedule_id}", response_model=AuditScheduleRead)
def delete_schedule(
    schedule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditScheduleRead:
    row = AuditScheduleService(db).soft_delete_schedule(organization.id, schedule_id, current_user.id)
    db.commit()
    return _schedule_read(row)


@router.get("/{schedule_id}/history", response_model=list[AuditEngagementRead])
def get_schedule_history(
    schedule_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditEngagementRead]:
    rows = AuditScheduleService(db).get_schedule_history(organization.id, schedule_id)
    return [_engagement_read(row) for row in rows[skip : skip + limit]]
