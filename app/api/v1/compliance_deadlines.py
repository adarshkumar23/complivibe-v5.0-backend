import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_deadline_event import ComplianceDeadlineEvent
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.compliance_deadline import (
    ComplianceDeadlineCancelRequest,
    ComplianceDeadlineCompleteRequest,
    ComplianceDeadlineCreate,
    ComplianceDeadlineEvaluateRequest,
    ComplianceDeadlineEvaluateResponse,
    ComplianceDeadlineEventRead,
    ComplianceDeadlineRead,
    ComplianceDeadlineSummary,
    ComplianceDeadlineUpdate,
    ComplianceDeadlineWaiveRequest,
)
from app.services.audit_service import AuditService
from app.services.compliance_deadline_service import ComplianceDeadlineService

router = APIRouter(prefix="/compliance/deadlines", tags=["compliance-deadlines"])


def _deadline_read(row: ComplianceDeadline) -> ComplianceDeadlineRead:
    return ComplianceDeadlineRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        description=row.description,
        deadline_type=row.deadline_type,
        due_date=row.due_date,
        status=row.status,
        priority=row.priority,
        owner_user_id=row.owner_user_id,
        linked_entity_type=row.linked_entity_type,
        linked_entity_id=row.linked_entity_id,
        reminder_days_before=row.reminder_days_before,
        last_reminder_at=row.last_reminder_at,
        completed_at=row.completed_at,
        completed_by_user_id=row.completed_by_user_id,
        completion_notes=row.completion_notes,
        waiver_reason=row.waiver_reason,
        cancelled_at=row.cancelled_at,
        cancelled_by_user_id=row.cancelled_by_user_id,
        cancellation_reason=row.cancellation_reason,
        tags_json=row.tags_json,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_read(row: ComplianceDeadlineEvent) -> ComplianceDeadlineEventRead:
    return ComplianceDeadlineEventRead(
        id=row.id,
        organization_id=row.organization_id,
        deadline_id=row.deadline_id,
        event_type=row.event_type,
        dry_run=row.dry_run,
        outbox_queued=row.outbox_queued,
        event_metadata_json=row.event_metadata_json,
        created_at=row.created_at,
    )


@router.post("", response_model=ComplianceDeadlineRead, status_code=status.HTTP_201_CREATED)
def create_deadline(
    payload: ComplianceDeadlineCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:write")),
) -> ComplianceDeadlineRead:
    service = ComplianceDeadlineService(db)
    service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)
    service.validate_linked_entity(
        organization_id=organization.id,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
    )

    row = ComplianceDeadline(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        deadline_type=payload.deadline_type,
        due_date=payload.due_date,
        status="upcoming",
        priority=payload.priority,
        owner_user_id=payload.owner_user_id,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        reminder_days_before=payload.reminder_days_before,
        tags_json=payload.tags_json,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_deadline.created",
        entity_type="compliance_deadline",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"title": row.title, "status": row.status, "due_date": str(row.due_date), "priority": row.priority},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _deadline_read(row)


@router.get("/events", response_model=list[ComplianceDeadlineEventRead])
def list_deadline_events(
    deadline_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    dry_run: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:read")),
) -> list[ComplianceDeadlineEventRead]:
    stmt = select(ComplianceDeadlineEvent).where(ComplianceDeadlineEvent.organization_id == organization.id)
    if deadline_id is not None:
        stmt = stmt.where(ComplianceDeadlineEvent.deadline_id == deadline_id)
    if event_type is not None:
        stmt = stmt.where(ComplianceDeadlineEvent.event_type == event_type)
    if dry_run is not None:
        stmt = stmt.where(ComplianceDeadlineEvent.dry_run == dry_run)

    rows = db.execute(stmt.order_by(ComplianceDeadlineEvent.created_at.desc())).scalars().all()
    return [_event_read(row) for row in rows]


@router.get("/summary", response_model=ComplianceDeadlineSummary)
def compliance_deadline_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:read")),
) -> ComplianceDeadlineSummary:
    return ComplianceDeadlineSummary(**ComplianceDeadlineService(db).summary(organization.id))


@router.post("/evaluate-due", response_model=ComplianceDeadlineEvaluateResponse)
def evaluate_due_deadlines(
    payload: ComplianceDeadlineEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:write")),
) -> ComplianceDeadlineEvaluateResponse:
    service = ComplianceDeadlineService(db)
    result = service.evaluate_due(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        dry_run=payload.dry_run,
    )

    AuditService(db).write_audit_log(
        action="compliance_deadline.evaluated",
        entity_type="compliance_deadline",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json=result,
        metadata_json={"source": "api", "dry_run": payload.dry_run},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return ComplianceDeadlineEvaluateResponse(dry_run=payload.dry_run, **result)


@router.get("", response_model=list[ComplianceDeadlineRead])
def list_deadlines(
    status_filter: str | None = Query(default=None, alias="status"),
    deadline_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None, alias="owner"),
    due_before: date | None = Query(default=None),
    due_after: date | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:read")),
) -> list[ComplianceDeadlineRead]:
    service = ComplianceDeadlineService(db)
    today = service.utcdate()

    stmt = select(ComplianceDeadline).where(ComplianceDeadline.organization_id == organization.id)
    if status_filter is not None:
        stmt = stmt.where(ComplianceDeadline.status == status_filter)
    if deadline_type is not None:
        stmt = stmt.where(ComplianceDeadline.deadline_type == deadline_type)
    if priority is not None:
        stmt = stmt.where(ComplianceDeadline.priority == priority)
    if owner_user_id is not None:
        stmt = stmt.where(ComplianceDeadline.owner_user_id == owner_user_id)
    if due_before is not None:
        stmt = stmt.where(ComplianceDeadline.due_date <= due_before)
    if due_after is not None:
        stmt = stmt.where(ComplianceDeadline.due_date >= due_after)
    if overdue_only:
        stmt = stmt.where(ComplianceDeadline.status == "overdue")

    rows = db.execute(stmt.order_by(ComplianceDeadline.due_date.asc(), ComplianceDeadline.created_at.desc())).scalars().all()

    if overdue_only:
        rows = [row for row in rows if row.due_date < today and row.status in {"upcoming", "overdue"}]

    return [_deadline_read(row) for row in rows]


@router.get("/{deadline_id}", response_model=ComplianceDeadlineRead)
def get_deadline(
    deadline_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:read")),
) -> ComplianceDeadlineRead:
    row = ComplianceDeadlineService(db).require_deadline_in_org(organization.id, deadline_id)
    return _deadline_read(row)


@router.patch("/{deadline_id}", response_model=ComplianceDeadlineRead)
def update_deadline(
    deadline_id: uuid.UUID,
    payload: ComplianceDeadlineUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:write")),
) -> ComplianceDeadlineRead:
    service = ComplianceDeadlineService(db)
    row = service.require_deadline_in_org(organization.id, deadline_id)
    service.ensure_not_terminal(row)

    changes = payload.model_dump(exclude_unset=True)
    owner_user_id = changes.get("owner_user_id")
    linked_entity_type = changes.get("linked_entity_type", row.linked_entity_type)
    linked_entity_id = changes.get("linked_entity_id", row.linked_entity_id)

    if owner_user_id is not None:
        service.ensure_owner_is_active_member(organization.id, owner_user_id)
    if "linked_entity_type" in changes or "linked_entity_id" in changes:
        service.validate_linked_entity(
            organization_id=organization.id,
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
        )

    before = {
        "title": row.title,
        "due_date": str(row.due_date),
        "priority": row.priority,
        "owner_user_id": str(row.owner_user_id),
    }
    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_deadline.updated",
        entity_type="compliance_deadline",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"title": row.title, "due_date": str(row.due_date), "priority": row.priority, "owner_user_id": str(row.owner_user_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _deadline_read(row)


@router.post("/{deadline_id}/complete", response_model=ComplianceDeadlineRead)
def complete_deadline(
    deadline_id: uuid.UUID,
    payload: ComplianceDeadlineCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:write")),
) -> ComplianceDeadlineRead:
    service = ComplianceDeadlineService(db)
    row = service.require_deadline_in_org(organization.id, deadline_id)
    service.ensure_not_terminal(row)

    row.status = "completed"
    row.completed_at = service.utcnow()
    row.completed_by_user_id = current_user.id
    row.completion_notes = payload.completion_notes

    event = ComplianceDeadlineEvent(
        organization_id=organization.id,
        deadline_id=row.id,
        event_type="completed",
        dry_run=False,
        outbox_queued=False,
        event_metadata_json={"source": "api"},
    )
    db.add(event)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_deadline.completed",
        entity_type="compliance_deadline",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "completed_at": row.completed_at.isoformat()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _deadline_read(row)


@router.post("/{deadline_id}/waive", response_model=ComplianceDeadlineRead)
def waive_deadline(
    deadline_id: uuid.UUID,
    payload: ComplianceDeadlineWaiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:write")),
) -> ComplianceDeadlineRead:
    service = ComplianceDeadlineService(db)
    row = service.require_deadline_in_org(organization.id, deadline_id)
    service.ensure_not_terminal(row)

    row.status = "waived"
    row.waiver_reason = payload.waiver_reason

    event = ComplianceDeadlineEvent(
        organization_id=organization.id,
        deadline_id=row.id,
        event_type="waived",
        dry_run=False,
        outbox_queued=False,
        event_metadata_json={"source": "api"},
    )
    db.add(event)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_deadline.waived",
        entity_type="compliance_deadline",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "waiver_reason": row.waiver_reason},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _deadline_read(row)


@router.post("/{deadline_id}/cancel", response_model=ComplianceDeadlineRead)
def cancel_deadline(
    deadline_id: uuid.UUID,
    payload: ComplianceDeadlineCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_deadlines:write")),
) -> ComplianceDeadlineRead:
    service = ComplianceDeadlineService(db)
    row = service.require_deadline_in_org(organization.id, deadline_id)
    service.ensure_not_terminal(row)

    row.status = "cancelled"
    row.cancelled_at = service.utcnow()
    row.cancelled_by_user_id = current_user.id
    row.cancellation_reason = payload.cancellation_reason

    event = ComplianceDeadlineEvent(
        organization_id=organization.id,
        deadline_id=row.id,
        event_type="cancelled",
        dry_run=False,
        outbox_queued=False,
        event_metadata_json={"source": "api"},
    )
    db.add(event)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_deadline.cancelled",
        entity_type="compliance_deadline",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "cancelled_at": row.cancelled_at.isoformat()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _deadline_read(row)
