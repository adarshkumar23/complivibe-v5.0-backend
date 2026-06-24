import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.email_delivery_event import EmailDeliveryEvent
from app.models.email_outbox import EmailOutbox
from app.models.email_template import EmailTemplate
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.email import (
    EmailDeliveryEventRead,
    EmailMarkFailedRequest,
    EmailOutboxCreate,
    EmailOutboxDetail,
    EmailOutboxRead,
    EmailTemplateCreate,
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
    WorkerActionResponse,
    WorkerClaimRequest,
    WorkerCompleteRequest,
    WorkerDeadLetterRequest,
    WorkerFailRequest,
    WorkerReleaseExpiredLocksResponse,
)
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
from app.services.email_worker_service import EmailWorkerService
from app.services.seed_service import SeedService

router = APIRouter(prefix="/email", tags=["email"])


def _template_read(template: EmailTemplate) -> EmailTemplateRead:
    return EmailTemplateRead(
        id=template.id,
        organization_id=template.organization_id,
        template_key=template.template_key,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        body_text_template=template.body_text_template,
        body_html_template=template.body_html_template,
        allowed_variables_json=template.allowed_variables_json or [],
        status=template.status,
        version=template.version,
        created_by_user_id=template.created_by_user_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _outbox_read(item: EmailOutbox) -> EmailOutboxRead:
    return EmailOutboxRead(
        id=item.id,
        organization_id=item.organization_id,
        template_id=item.template_id,
        event_type=item.event_type,
        recipient_email=item.recipient_email,
        recipient_user_id=item.recipient_user_id,
        subject=item.subject,
        body_text=item.body_text,
        body_html=item.body_html,
        status=item.status,
        priority=item.priority,
        scheduled_at=item.scheduled_at,
        queued_at=item.queued_at,
        sent_at=item.sent_at,
        failed_at=item.failed_at,
        cancelled_at=item.cancelled_at,
        locked_at=item.locked_at,
        locked_by=item.locked_by,
        lock_expires_at=item.lock_expires_at,
        last_attempt_at=item.last_attempt_at,
        next_attempt_at=item.next_attempt_at,
        dead_lettered_at=item.dead_lettered_at,
        attempt_count=item.attempt_count,
        max_attempts=item.max_attempts,
        last_error=item.last_error,
        provider=item.provider,
        provider_message_id=item.provider_message_id,
        metadata_json=item.metadata_json,
        worker_metadata_json=item.worker_metadata_json,
        created_by_user_id=item.created_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _event_read(event: EmailDeliveryEvent) -> EmailDeliveryEventRead:
    return EmailDeliveryEventRead(
        id=event.id,
        organization_id=event.organization_id,
        email_outbox_id=event.email_outbox_id,
        event_type=event.event_type,
        status_from=event.status_from,
        status_to=event.status_to,
        details_json=event.details_json,
        created_by_user_id=event.created_by_user_id,
        created_at=event.created_at,
    )


def _get_template_for_org(db: Session, organization_id: uuid.UUID, template_id: uuid.UUID) -> EmailTemplate:
    template = db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id)).scalar_one_or_none()
    if template is None or template.organization_id not in (None, organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
    return template


def _get_outbox_for_org(db: Session, organization_id: uuid.UUID, email_id: uuid.UUID) -> EmailOutbox:
    item = db.execute(select(EmailOutbox).where(EmailOutbox.id == email_id)).scalar_one_or_none()
    if item is None or item.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email outbox message not found")
    return item


@router.get("/templates", response_model=list[EmailTemplateRead])
def list_templates(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:read")),
) -> list[EmailTemplateRead]:
    SeedService.ensure_global_email_templates(db)
    db.commit()

    stmt = (
        select(EmailTemplate)
        .where(or_(EmailTemplate.organization_id == organization.id, EmailTemplate.organization_id.is_(None)))
        .order_by(EmailTemplate.template_key.asc(), EmailTemplate.version.desc())
    )
    templates = db.execute(stmt).scalars().all()
    return [_template_read(tpl) for tpl in templates]


@router.post("/templates", response_model=EmailTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: EmailTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:admin")),
) -> EmailTemplateRead:
    template = EmailTemplate(
        organization_id=organization.id,
        template_key=payload.template_key,
        name=payload.name,
        description=payload.description,
        subject_template=payload.subject_template,
        body_text_template=payload.body_text_template,
        body_html_template=payload.body_html_template,
        allowed_variables_json=payload.allowed_variables_json,
        status=payload.status,
        version=1,
        created_by_user_id=current_user.id,
    )
    db.add(template)
    db.flush()

    AuditService(db).write_audit_log(
        action="email_template.created",
        entity_type="email_template",
        entity_id=template.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"template_key": template.template_key, "status": template.status, "version": template.version},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(template)
    return _template_read(template)


@router.patch("/templates/{template_id}", response_model=EmailTemplateRead)
def update_template(
    template_id: uuid.UUID,
    payload: EmailTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:admin")),
) -> EmailTemplateRead:
    template = _get_template_for_org(db, organization.id, template_id)
    if template.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global templates cannot be modified by organization users")

    before = {
        "name": template.name,
        "description": template.description,
        "subject_template": template.subject_template,
        "status": template.status,
    }

    for field in ["name", "description", "subject_template", "body_text_template", "body_html_template", "allowed_variables_json", "status"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(template, field, value)

    db.flush()

    AuditService(db).write_audit_log(
        action="email_template.updated",
        entity_type="email_template",
        entity_id=template.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"name": template.name, "status": template.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(template)
    return _template_read(template)


@router.post("/templates/{template_id}/preview", response_model=EmailTemplatePreviewResponse)
def preview_template(
    template_id: uuid.UUID,
    payload: EmailTemplatePreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:read")),
) -> EmailTemplatePreviewResponse:
    template = _get_template_for_org(db, organization.id, template_id)
    rendered = EmailService(db).render_template(template, payload.variables_json)
    return EmailTemplatePreviewResponse(
        subject=str(rendered["subject"]),
        body_text=str(rendered["body_text"]),
        body_html=rendered["body_html"],
    )


@router.post("/outbox", response_model=EmailOutboxRead, status_code=status.HTTP_201_CREATED)
def queue_email(
    payload: EmailOutboxCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:write")),
) -> EmailOutboxRead:
    SeedService.ensure_global_email_templates(db)
    service = EmailService(db)
    template = service.resolve_template_for_org(
        organization_id=organization.id,
        template_id=payload.template_id,
        template_key=payload.template_key,
    )

    outbox = service.queue_email(
        organization_id=organization.id,
        template=template,
        event_type=payload.event_type,
        recipient_email=str(payload.recipient_email),
        recipient_user_id=payload.recipient_user_id,
        priority=payload.priority,
        scheduled_at=payload.scheduled_at,
        metadata_json=payload.metadata_json,
        created_by_user_id=current_user.id,
        variables_json=payload.variables_json,
        initial_status=payload.initial_status,
    )

    AuditService(db).write_audit_log(
        action="email.queued",
        entity_type="email_outbox",
        entity_id=outbox.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "template_id": str(template.id),
            "event_type": outbox.event_type,
            "recipient_email": outbox.recipient_email,
            "status": outbox.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(outbox)
    return _outbox_read(outbox)


@router.get("/outbox", response_model=list[EmailOutboxRead])
def list_outbox(
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = Query(default=None),
    recipient_email: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:read")),
) -> list[EmailOutboxRead]:
    stmt = select(EmailOutbox).where(EmailOutbox.organization_id == organization.id)
    if status_filter:
        stmt = stmt.where(EmailOutbox.status == status_filter)
    if event_type:
        stmt = stmt.where(EmailOutbox.event_type == event_type)
    if recipient_email:
        stmt = stmt.where(EmailOutbox.recipient_email == recipient_email)

    stmt = stmt.order_by(EmailOutbox.created_at.desc()).offset(offset).limit(limit)
    outbox_rows = db.execute(stmt).scalars().all()
    return [_outbox_read(row) for row in outbox_rows]


@router.get("/outbox/{email_id}", response_model=EmailOutboxDetail)
def outbox_detail(
    email_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:read")),
) -> EmailOutboxDetail:
    item = _get_outbox_for_org(db, organization.id, email_id)
    events = db.execute(
        select(EmailDeliveryEvent)
        .where(EmailDeliveryEvent.email_outbox_id == item.id)
        .order_by(EmailDeliveryEvent.created_at.asc())
    ).scalars().all()

    return EmailOutboxDetail(**_outbox_read(item).model_dump(), delivery_events=[_event_read(evt) for evt in events])


@router.post("/outbox/{email_id}/cancel", response_model=EmailOutboxRead)
def cancel_email(
    email_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:write")),
) -> EmailOutboxRead:
    item = _get_outbox_for_org(db, organization.id, email_id)
    if item.status not in {"draft", "pending", "failed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email cannot be cancelled from current status")

    previous_status = item.status
    item.status = "cancelled"
    item.cancelled_at = datetime.now(UTC)

    EmailService(db).add_delivery_event(
        organization_id=organization.id,
        email_outbox_id=item.id,
        event_type="cancelled",
        status_from=previous_status,
        status_to=item.status,
        details_json=None,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="email.cancelled",
        entity_type="email_outbox",
        entity_id=item.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": previous_status},
        after_json={"status": item.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(item)
    return _outbox_read(item)


@router.post("/outbox/{email_id}/mark-sent", response_model=EmailOutboxRead)
def mark_sent(
    email_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> EmailOutboxRead:
    item = _get_outbox_for_org(db, organization.id, email_id)
    previous_status = item.status
    item.status = "sent"
    item.sent_at = datetime.now(UTC)

    EmailService(db).add_delivery_event(
        organization_id=organization.id,
        email_outbox_id=item.id,
        event_type="marked_sent",
        status_from=previous_status,
        status_to=item.status,
        details_json={"manual": True},
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="email.marked_sent",
        entity_type="email_outbox",
        entity_id=item.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": previous_status},
        after_json={"status": item.status},
        metadata_json={"source": "api", "manual": True},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(item)
    return _outbox_read(item)


@router.post("/outbox/{email_id}/mark-failed", response_model=EmailOutboxRead)
def mark_failed(
    email_id: uuid.UUID,
    payload: EmailMarkFailedRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> EmailOutboxRead:
    item = _get_outbox_for_org(db, organization.id, email_id)
    previous_status = item.status
    item.status = "failed"
    item.failed_at = datetime.now(UTC)
    item.last_error = payload.error_message
    item.attempt_count += 1

    EmailService(db).add_delivery_event(
        organization_id=organization.id,
        email_outbox_id=item.id,
        event_type="marked_failed",
        status_from=previous_status,
        status_to=item.status,
        details_json={"error": payload.error_message},
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="email.marked_failed",
        entity_type="email_outbox",
        entity_id=item.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": previous_status},
        after_json={"status": item.status, "attempt_count": item.attempt_count},
        metadata_json={"source": "api", "manual": True},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(item)
    return _outbox_read(item)


@router.post("/worker/claim", response_model=list[EmailOutboxRead])
def worker_claim(
    payload: WorkerClaimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> list[EmailOutboxRead]:
    service = EmailWorkerService(db)
    claimed = service.claim_pending_emails(
        organization_id=organization.id,
        worker_id=payload.worker_id,
        limit=payload.limit,
        actor_user_id=current_user.id,
    )
    db.commit()
    return [_outbox_read(item) for item in claimed]


@router.post("/worker/{email_id}/complete", response_model=WorkerActionResponse)
def worker_complete(
    email_id: uuid.UUID,
    payload: WorkerCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> WorkerActionResponse:
    item = _get_outbox_for_org(db, organization.id, email_id)
    service = EmailWorkerService(db)
    service.complete_email(
        email=item,
        worker_id=payload.worker_id,
        actor_user_id=current_user.id,
        provider_message_id=payload.provider_message_id,
    )

    AuditService(db).write_audit_log(
        action="email.worker_completed",
        entity_type="email_outbox",
        entity_id=item.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": "processing"},
        after_json={"status": item.status},
        metadata_json={"source": "api", "worker_id": payload.worker_id},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(item)
    return WorkerActionResponse(email=_outbox_read(item))


@router.post("/worker/{email_id}/fail", response_model=WorkerActionResponse)
def worker_fail(
    email_id: uuid.UUID,
    payload: WorkerFailRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> WorkerActionResponse:
    item = _get_outbox_for_org(db, organization.id, email_id)
    service = EmailWorkerService(db)
    was_dead_letter = item.attempt_count + 1 >= item.max_attempts
    service.fail_email(
        email=item,
        worker_id=payload.worker_id,
        error_message=payload.error_message,
        retry_after_seconds=payload.retry_after_seconds,
        actor_user_id=current_user.id,
    )

    action = "email.dead_lettered" if was_dead_letter else "email.worker_failed"
    after_json = {"status": item.status, "attempt_count": item.attempt_count}
    if item.next_attempt_at is not None:
        after_json["next_attempt_at"] = item.next_attempt_at.isoformat()

    AuditService(db).write_audit_log(
        action=action,
        entity_type="email_outbox",
        entity_id=item.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": "processing", "attempt_count": item.attempt_count - 1},
        after_json=after_json,
        metadata_json={"source": "api", "worker_id": payload.worker_id},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(item)
    return WorkerActionResponse(email=_outbox_read(item))


@router.post("/worker/release-expired-locks", response_model=WorkerReleaseExpiredLocksResponse)
def worker_release_expired_locks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> WorkerReleaseExpiredLocksResponse:
    service = EmailWorkerService(db)
    released = service.release_expired_locks(
        organization_id=organization.id,
        actor_user_id=current_user.id,
    )

    if released:
        AuditService(db).write_audit_log(
            action="email.expired_lock_released",
            entity_type="email_outbox",
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"released_count": len(released)},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    db.commit()
    return WorkerReleaseExpiredLocksResponse(released_count=len(released), emails=[_outbox_read(item) for item in released])


@router.post("/worker/{email_id}/dead-letter", response_model=WorkerActionResponse)
def worker_dead_letter(
    email_id: uuid.UUID,
    payload: WorkerDeadLetterRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:send")),
) -> WorkerActionResponse:
    item = _get_outbox_for_org(db, organization.id, email_id)
    service = EmailWorkerService(db)
    previous = item.status
    service.move_to_dead_letter(
        email=item,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="email.dead_lettered",
        entity_type="email_outbox",
        entity_id=item.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": previous},
        after_json={"status": item.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(item)
    return WorkerActionResponse(email=_outbox_read(item))
