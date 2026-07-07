import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.task import Task
from app.models.user import User
from app.repositories.task_repository import TaskRepository
from app.schemas.task import (
    TaskCancelRequest,
    TaskCompleteRequest,
    TaskCreate,
    TaskDetail,
    TaskNotifyResponse,
    TaskRead,
    TaskReminderQueueRequest,
    TaskReminderQueueResponse,
    TaskSummary,
    TaskUpdate,
)
from app.services.audit_service import AuditService
from app.services.seed_service import SeedService
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


_OPEN_TASK_STATUSES = ("open", "in_progress", "blocked")

# Linked-entity statuses that indicate the underlying risk/control has
# already been resolved through its own workflow, independent of this task.
_RISK_RESOLVED_STATUSES = {"accepted", "mitigated", "archived"}
_CONTROL_RESOLVED_STATUSES = {"implemented", "not_applicable", "archived"}


def _task_read(task: Task) -> TaskRead:
    now = datetime.now(UTC)
    is_overdue = False
    overdue_by_hours: float | None = None
    if task.status in _OPEN_TASK_STATUSES and task.due_date is not None:
        due_date = task.due_date if task.due_date.tzinfo is not None else task.due_date.replace(tzinfo=UTC)
        if due_date < now:
            is_overdue = True
            overdue_by_hours = round((now - due_date).total_seconds() / 3600.0, 2)

    return TaskRead(
        id=task.id,
        organization_id=task.organization_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        task_type=task.task_type,
        owner_user_id=task.owner_user_id,
        created_by_user_id=task.created_by_user_id,
        due_date=task.due_date,
        completed_at=task.completed_at,
        completed_by_user_id=task.completed_by_user_id,
        cancelled_at=task.cancelled_at,
        cancelled_by_user_id=task.cancelled_by_user_id,
        linked_entity_type=task.linked_entity_type,
        linked_entity_id=task.linked_entity_id,
        source=task.source,
        reminder_status=task.reminder_status,
        last_reminder_at=task.last_reminder_at,
        metadata_json=task.metadata_json,
        created_at=task.created_at,
        updated_at=task.updated_at,
        is_overdue=is_overdue,
        overdue_by_hours=overdue_by_hours,
    )


def _get_task_or_404(db: Session, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = TaskRepository(db).get_by_id(task_id)
    if task is None or task.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _get_task_for_update_or_404(db: Session, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = TaskRepository(db).get_by_id_for_update(task_id)
    if task is None or task.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("/summary", response_model=TaskSummary)
def task_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:read")),
) -> TaskSummary:
    return TaskSummary(**TaskService(db).summary(organization.id))


@router.post("/reminders/queue", response_model=TaskReminderQueueResponse)
def queue_task_reminders(
    payload: TaskReminderQueueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:write")),
) -> TaskReminderQueueResponse:
    now = datetime.now(UTC)
    due_cutoff = now + timedelta(days=payload.due_within_days)

    stmt = (
        select(Task)
        .where(
            Task.organization_id == organization.id,
            Task.status.in_(["open", "in_progress", "blocked"]),
            Task.owner_user_id.is_not(None),
            Task.due_date.is_not(None),
        )
        .order_by(Task.due_date.asc())
        .limit(payload.limit)
    )
    if payload.overdue_only:
        stmt = stmt.where(Task.due_date < now)
    else:
        stmt = stmt.where(Task.due_date <= due_cutoff)

    tasks = db.execute(stmt).scalars().all()
    SeedService.ensure_global_email_templates(db)

    service = TaskService(db)
    outbox_ids: list[uuid.UUID] = []
    for task in tasks:
        if task.owner_user_id is None:
            continue
        owner = db.execute(select(User).where(User.id == task.owner_user_id)).scalar_one_or_none()
        if owner is None or not owner.email:
            continue
        outbox_id = service.queue_task_notification(
            organization_id=organization.id,
            created_by_user_id=current_user.id,
            owner_user=owner,
            task_title=task.title,
            template_key="task_assigned",
            event_type="task.reminder",
        )
        task.last_reminder_at = now
        task.reminder_status = "sent"
        outbox_ids.append(outbox_id)

    AuditService(db).write_audit_log(
        action="task.reminders_queued",
        entity_type="task",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"queued_count": len(outbox_ids)},
        metadata_json={"source": "api", "overdue_only": payload.overdue_only, "due_within_days": payload.due_within_days},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return TaskReminderQueueResponse(queued_count=len(outbox_ids), outbox_email_ids=outbox_ids)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    linked_entity_type: str | None = Query(default=None),
    linked_entity_id: uuid.UUID | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    due_before: datetime | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:read")),
) -> list[TaskRead]:
    rows = TaskRepository(db).list_by_organization(
        organization.id,
        status=status,
        priority=priority,
        task_type=task_type,
        owner_user_id=owner_user_id,
        linked_entity_type=linked_entity_type,
        linked_entity_id=linked_entity_id,
        overdue_only=overdue_only,
        due_before=due_before,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [_task_read(t) for t in rows]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:write")),
) -> TaskRead:
    service = TaskService(db)
    owner_user = service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)
    service.validate_linked_entity(
        organization_id=organization.id,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
    )

    task = Task(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        status="open",
        priority=payload.priority,
        task_type=payload.task_type,
        owner_user_id=payload.owner_user_id,
        created_by_user_id=current_user.id,
        due_date=payload.due_date,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        source="manual",
        reminder_status="none",
        metadata_json=payload.metadata_json,
    )
    db.add(task)
    db.flush()

    outbox_id = None
    if payload.notify_assignee and owner_user is not None:
        SeedService.ensure_global_email_templates(db)
        outbox_id = service.queue_task_notification(
            organization_id=organization.id,
            created_by_user_id=current_user.id,
            owner_user=owner_user,
            task_title=task.title,
        )

    AuditService(db).write_audit_log(
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"title": task.title, "status": task.status, "priority": task.priority},
        metadata_json={"source": "api", "notification_outbox_id": str(outbox_id) if outbox_id else None},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(task)
    return _task_read(task)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task_detail(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:read")),
) -> TaskDetail:
    task = _get_task_or_404(db, organization.id, task_id)
    linked_summary = None
    linked_entity_stale = False
    if task.linked_entity_type and task.linked_entity_id:
        try:
            linked_summary = TaskService(db).validate_linked_entity(
                organization_id=organization.id,
                linked_entity_type=task.linked_entity_type,
                linked_entity_id=task.linked_entity_id,
            )
        except HTTPException:
            linked_summary = None

        if (
            linked_summary is not None
            and task.status in _OPEN_TASK_STATUSES
        ):
            entity_status = linked_summary.get("status")
            if task.linked_entity_type == "risk" and entity_status in _RISK_RESOLVED_STATUSES:
                linked_entity_stale = True
            elif task.linked_entity_type == "control" and entity_status in _CONTROL_RESOLVED_STATUSES:
                linked_entity_stale = True

    return TaskDetail(
        **_task_read(task).model_dump(),
        linked_entity_summary=linked_summary,
        linked_entity_stale=linked_entity_stale,
    )


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:write")),
) -> TaskRead:
    task = _get_task_for_update_or_404(db, organization.id, task_id)
    service = TaskService(db)

    if payload.owner_user_id is not None:
        service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)

    before = {
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "owner_user_id": str(task.owner_user_id) if task.owner_user_id else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }

    status_before = task.status
    for field in ["title", "description", "status", "priority", "owner_user_id", "due_date", "metadata_json"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(task, field, value)

    if payload.status == "completed" and status_before != "completed":
        task.completed_at = datetime.now(UTC)
        task.completed_by_user_id = current_user.id
    if payload.status == "cancelled" and status_before != "cancelled":
        task.cancelled_at = datetime.now(UTC)
        task.cancelled_by_user_id = current_user.id

    db.flush()

    after = {
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "owner_user_id": str(task.owner_user_id) if task.owner_user_id else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }

    AuditService(db).write_audit_log(
        action="task.updated",
        entity_type="task",
        entity_id=task.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json=after,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(task)
    return _task_read(task)


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(
    task_id: uuid.UUID,
    payload: TaskCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:write")),
) -> TaskRead:
    task = _get_task_for_update_or_404(db, organization.id, task_id)
    if task.status == "completed":
        # Two concurrent "complete" calls on the same task: the row lock
        # serializes them, and the second one (now seeing the committed
        # first) is rejected instead of silently re-stamping completed_at
        # and completed_by_user_id with its own actor/time.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task is already completed")
    before_status = task.status

    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    task.completed_by_user_id = current_user.id

    metadata = dict(task.metadata_json or {})
    if payload.completion_notes:
        metadata["completion_notes"] = payload.completion_notes
    task.metadata_json = metadata
    db.flush()

    AuditService(db).write_audit_log(
        action="task.completed",
        entity_type="task",
        entity_id=task.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": task.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(task)
    return _task_read(task)


@router.post("/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: uuid.UUID,
    payload: TaskCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:write")),
) -> TaskRead:
    task = _get_task_for_update_or_404(db, organization.id, task_id)
    if task.status == "cancelled":
        # Same race protection as complete_task, mirrored for cancel: the row
        # lock serializes two concurrent cancels and the second is rejected
        # rather than silently re-stamping cancelled_at/cancelled_by_user_id.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task is already cancelled")
    before_status = task.status

    task.status = "cancelled"
    task.cancelled_at = datetime.now(UTC)
    task.cancelled_by_user_id = current_user.id
    metadata = dict(task.metadata_json or {})
    metadata["cancellation_reason"] = payload.cancellation_reason
    task.metadata_json = metadata
    db.flush()

    AuditService(db).write_audit_log(
        action="task.cancelled",
        entity_type="task",
        entity_id=task.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": task.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(task)
    return _task_read(task)


@router.post("/{task_id}/notify", response_model=TaskNotifyResponse)
def notify_task_assignee(
    task_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("tasks:write")),
) -> TaskNotifyResponse:
    task = _get_task_or_404(db, organization.id, task_id)
    if task.owner_user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task has no assignee")

    owner = db.execute(select(User).where(User.id == task.owner_user_id)).scalar_one_or_none()
    if owner is None or not owner.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task assignee has no email")

    SeedService.ensure_global_email_templates(db)
    outbox_id = TaskService(db).queue_task_notification(
        organization_id=organization.id,
        created_by_user_id=current_user.id,
        owner_user=owner,
        task_title=task.title,
        template_key="task_assigned",
        event_type="task.reminder",
    )

    task.last_reminder_at = datetime.now(UTC)
    task.reminder_status = "sent"
    db.flush()

    AuditService(db).write_audit_log(
        action="task.notification_queued",
        entity_type="task",
        entity_id=task.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": task.status},
        metadata_json={"source": "api", "outbox_email_id": str(outbox_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return TaskNotifyResponse(task_id=task.id, outbox_email_id=outbox_id, status="queued")
