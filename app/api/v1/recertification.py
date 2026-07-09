import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.evidence_recertification_policy import EvidenceRecertificationPolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.recertification_action_log import RecertificationActionLog
from app.models.recertification_run import RecertificationRun
from app.models.user import User
from app.repositories.recertification_repository import RecertificationRepository
from app.schemas.recertification import (
    ControlReassessmentRunRequest,
    DueControlReassessmentRead,
    DueEvidenceItemRead,
    RecertificationActionLogRead,
    RecertificationPolicyCreate,
    RecertificationPolicyRead,
    RecertificationPolicyUpdate,
    RecertificationRunDetail,
    RecertificationRunRead,
    RecertificationRunRequest,
    RecertificationSummary,
)
from app.services.audit_service import AuditService
from app.services.recertification_service import RecertificationService

router = APIRouter(prefix="/recertification", tags=["recertification"])


def _policy_read(row: EvidenceRecertificationPolicy) -> RecertificationPolicyRead:
    return RecertificationPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        scope_type=row.scope_type,
        scope_config_json=row.scope_config_json,
        cadence=row.cadence,
        lead_time_days=row.lead_time_days,
        owner_user_id=row.owner_user_id,
        status=row.status,
        last_run_at=row.last_run_at,
        next_run_at=row.next_run_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_read(row: RecertificationRun) -> RecertificationRunRead:
    return RecertificationRunRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        run_type=row.run_type,
        dry_run=row.dry_run,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        due_count=row.due_count,
        overdue_count=row.overdue_count,
        task_count=row.task_count,
        email_count=row.email_count,
        skipped_duplicate_count=row.skipped_duplicate_count,
        error_count=row.error_count,
        summary_json=row.summary_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _action_read(row: RecertificationActionLog) -> RecertificationActionLogRead:
    return RecertificationActionLogRead(
        id=row.id,
        organization_id=row.organization_id,
        run_id=row.run_id,
        policy_id=row.policy_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action_type=row.action_type,
        action_status=row.action_status,
        idempotency_key=row.idempotency_key,
        created_task_id=row.created_task_id,
        created_email_outbox_id=row.created_email_outbox_id,
        skipped_reason=row.skipped_reason,
        error_message=row.error_message,
        created_at=row.created_at,
    )


def _policy_or_404(db: Session, organization_id: uuid.UUID, policy_id: uuid.UUID) -> EvidenceRecertificationPolicy:
    policy = RecertificationRepository(db).get_policy(policy_id)
    if policy is None or policy.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recertification policy not found")
    return policy


def _run_or_404(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> RecertificationRun:
    run = RecertificationRepository(db).get_run(run_id)
    if run is None or run.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recertification run not found")
    return run


@router.post("/policies", response_model=RecertificationPolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: RecertificationPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> RecertificationPolicyRead:
    service = RecertificationService(db)
    service.validate_scope_type(payload.scope_type)
    service.validate_cadence(payload.cadence)
    service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)

    row = EvidenceRecertificationPolicy(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        scope_type=payload.scope_type,
        scope_config_json=payload.scope_config_json,
        cadence=payload.cadence,
        lead_time_days=payload.lead_time_days,
        owner_user_id=payload.owner_user_id,
        status=payload.status,
        next_run_at=service.calculate_next_run_at(payload.cadence),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="recertification_policy.created",
        entity_type="evidence_recertification_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"name": row.name, "scope_type": row.scope_type, "cadence": row.cadence, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/policies", response_model=list[RecertificationPolicyRead])
def list_policies(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> list[RecertificationPolicyRead]:
    rows = RecertificationRepository(db).list_policies(organization.id)
    return [_policy_read(row) for row in rows]


@router.patch("/policies/{policy_id}", response_model=RecertificationPolicyRead)
def update_policy(
    policy_id: uuid.UUID,
    payload: RecertificationPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> RecertificationPolicyRead:
    row = _policy_or_404(db, organization.id, policy_id)
    service = RecertificationService(db)

    if payload.scope_type is not None:
        service.validate_scope_type(payload.scope_type)
    if payload.cadence is not None:
        service.validate_cadence(payload.cadence)
    if payload.owner_user_id is not None:
        service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)

    before = {
        "name": row.name,
        "scope_type": row.scope_type,
        "cadence": row.cadence,
        "lead_time_days": row.lead_time_days,
        "status": row.status,
    }

    for field in [
        "name",
        "description",
        "scope_type",
        "scope_config_json",
        "cadence",
        "lead_time_days",
        "owner_user_id",
        "status",
    ]:
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)

    if payload.cadence is not None:
        row.next_run_at = service.calculate_next_run_at(row.cadence)

    db.flush()

    AuditService(db).write_audit_log(
        action="recertification_policy.updated",
        entity_type="evidence_recertification_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "scope_type": row.scope_type,
            "cadence": row.cadence,
            "lead_time_days": row.lead_time_days,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/policies/{policy_id}/archive", response_model=RecertificationPolicyRead)
def archive_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> RecertificationPolicyRead:
    row = _policy_or_404(db, organization.id, policy_id)
    before_status = row.status
    row.status = "archived"
    db.flush()

    AuditService(db).write_audit_log(
        action="recertification_policy.archived",
        entity_type="evidence_recertification_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/evidence/due", response_model=list[DueEvidenceItemRead])
def due_evidence(
    policy_id: uuid.UUID | None = Query(default=None),
    lead_time_days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> list[DueEvidenceItemRead]:
    policy = _policy_or_404(db, organization.id, policy_id) if policy_id else None
    service = RecertificationService(db)
    rows = service.discover_due_evidence(
        organization_id=organization.id,
        policy=policy,
        lead_time_days=policy.lead_time_days if policy else lead_time_days,
        limit=limit,
    )
    return [DueEvidenceItemRead(**row) for row in rows]


@router.post("/evidence/run", response_model=RecertificationRunRead)
def run_evidence(
    payload: RecertificationRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:execute")),
) -> RecertificationRunRead:
    policy = _policy_or_404(db, organization.id, payload.policy_id) if payload.policy_id else None

    service = RecertificationService(db)
    run = service.run_evidence_recertification(
        organization_id=organization.id,
        policy=policy,
        dry_run=payload.dry_run,
        notify_owner=payload.notify_owner,
        limit=payload.limit,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="recertification.evidence_run",
        entity_type="recertification_run",
        entity_id=run.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "run_type": run.run_type,
            "dry_run": run.dry_run,
            "due_count": run.due_count,
            "task_count": run.task_count,
            "email_count": run.email_count,
            "skipped_duplicate_count": run.skipped_duplicate_count,
            "error_count": run.error_count,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(run)
    return _run_read(run)


@router.get("/controls/due", response_model=list[DueControlReassessmentRead])
def due_controls(
    policy_id: uuid.UUID | None = Query(default=None),
    due_within_days: int = Query(default=7, ge=0, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> list[DueControlReassessmentRead]:
    policy = _policy_or_404(db, organization.id, policy_id) if policy_id else None
    rows = RecertificationService(db).discover_due_control_tests(
        organization_id=organization.id,
        due_within_days=due_within_days,
        limit=limit,
        policy=policy,
    )
    return [DueControlReassessmentRead(**row) for row in rows]


@router.post("/controls/run", response_model=RecertificationRunRead)
def run_controls(
    payload: ControlReassessmentRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:execute")),
) -> RecertificationRunRead:
    policy = _policy_or_404(db, organization.id, payload.policy_id) if payload.policy_id else None

    service = RecertificationService(db)
    run = service.run_control_reassessment(
        organization_id=organization.id,
        policy=policy,
        dry_run=payload.dry_run,
        notify_owner=payload.notify_owner,
        due_within_days=payload.due_within_days,
        limit=payload.limit,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="recertification.control_reassessment_run",
        entity_type="recertification_run",
        entity_id=run.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "run_type": run.run_type,
            "dry_run": run.dry_run,
            "due_count": run.due_count,
            "task_count": run.task_count,
            "email_count": run.email_count,
            "skipped_duplicate_count": run.skipped_duplicate_count,
            "error_count": run.error_count,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(run)
    return _run_read(run)


@router.get("/runs", response_model=list[RecertificationRunRead])
def list_runs(
    run_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    policy_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> list[RecertificationRunRead]:
    rows = RecertificationRepository(db).list_runs(
        organization.id,
        run_type=run_type,
        status=status_filter,
        policy_id=policy_id,
        limit=limit,
        offset=offset,
    )
    return [_run_read(row) for row in rows]


@router.get("/runs/{run_id}", response_model=RecertificationRunDetail)
def run_detail(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> RecertificationRunDetail:
    run = _run_or_404(db, organization.id, run_id)
    logs = RecertificationRepository(db).list_action_logs(organization.id, run.id)
    return RecertificationRunDetail(
        run=_run_read(run),
        action_logs=[_action_read(row) for row in logs],
    )


@router.get("/summary", response_model=RecertificationSummary)
def recertification_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> RecertificationSummary:
    return RecertificationSummary(**RecertificationService(db).summary(organization.id))
