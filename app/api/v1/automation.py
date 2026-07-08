import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.automation_action_log import AutomationActionLog
from app.models.automation_rule import AutomationRule
from app.models.automation_rule_execution import AutomationRuleExecution
from app.models.automation_rule_version import AutomationRuleVersion
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.automation import (
    AutomationActionLogRead,
    AutomationExecutionDetail,
    AutomationExecutionRead,
    AutomationRuleCreate,
    AutomationRuleRead,
    AutomationRuleScheduleUpdate,
    AutomationRuleUpdate,
    AutomationRuleVersionRead,
    AutomationRunResponse,
    AutomationScanResponse,
    AutomationScanRunRequest,
    AutomationScheduleSummary,
    AutomationSummary,
)
from app.services.audit_service import AuditService
from app.services.automation_service import AutomationService
from app.core.validation import validate_choice

router = APIRouter(prefix="/automation", tags=["automation"])


def _rule_read(payload: dict) -> AutomationRuleRead:
    return AutomationRuleRead(
        id=payload["id"],
        organization_id=payload["organization_id"],
        name=payload["name"],
        description=payload.get("description"),
        trigger_type=payload["trigger_type"],
        condition_type=payload["condition_type"],
        condition_config_json=payload.get("condition_config_json"),
        action_type=payload["action_type"],
        action_config_json=payload.get("action_config_json"),
        status=payload["status"],
        priority=payload["priority"],
        last_run_at=payload.get("last_run_at"),
        schedule_enabled=bool(payload["schedule_enabled"]),
        schedule_cadence=payload.get("schedule_cadence"),
        schedule_timezone=payload["schedule_timezone"],
        schedule_start_at=payload.get("schedule_start_at"),
        schedule_end_at=payload.get("schedule_end_at"),
        schedule_window_start=payload.get("schedule_window_start"),
        schedule_window_end=payload.get("schedule_window_end"),
        next_run_at=payload.get("next_run_at"),
        last_scheduled_run_at=payload.get("last_scheduled_run_at"),
        last_dry_run_at=payload.get("last_dry_run_at"),
        run_mode=payload["run_mode"],
        version=int(payload["version"]),
        version_notes=payload.get("version_notes"),
        created_by_user_id=payload.get("created_by_user_id"),
        stale_rule=bool(payload.get("stale_rule", False)),
        hours_since_last_run=float(payload["hours_since_last_run"]) if payload.get("hours_since_last_run") is not None else None,
        schedule_overdue=bool(payload.get("schedule_overdue", False)),
        schedule_drift_minutes=float(payload["schedule_drift_minutes"]) if payload.get("schedule_drift_minutes") is not None else None,
        context_flags=[str(item) for item in payload.get("context_flags", [])],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )


def _version_read(row: AutomationRuleVersion) -> AutomationRuleVersionRead:
    return AutomationRuleVersionRead(
        id=row.id,
        organization_id=row.organization_id,
        rule_id=row.rule_id,
        version=row.version,
        name=row.name,
        description=row.description,
        trigger_type=row.trigger_type,
        condition_type=row.condition_type,
        condition_config_json=row.condition_config_json,
        action_type=row.action_type,
        action_config_json=row.action_config_json,
        schedule_config_json=row.schedule_config_json,
        status=row.status,
        version_notes=row.version_notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _execution_read(payload: dict) -> AutomationExecutionRead:
    return AutomationExecutionRead(
        id=payload["id"],
        organization_id=payload["organization_id"],
        rule_id=payload["rule_id"],
        status=payload["status"],
        started_at=payload["started_at"],
        finished_at=payload.get("finished_at"),
        matched_count=int(payload["matched_count"]),
        action_count=int(payload["action_count"]),
        skipped_count=int(payload["skipped_count"]),
        error_count=int(payload["error_count"]),
        idempotency_key=payload.get("idempotency_key"),
        trigger_source=payload["trigger_source"],
        dry_run=bool(payload["dry_run"]),
        rule_version=payload.get("rule_version"),
        scheduled_run_at=payload.get("scheduled_run_at"),
        idempotency_scope=payload.get("idempotency_scope"),
        summary_json=payload.get("summary_json"),
        created_by_user_id=payload.get("created_by_user_id"),
        duration_seconds=float(payload["duration_seconds"]) if payload.get("duration_seconds") is not None else None,
        success_ratio=float(payload.get("success_ratio", 0)),
        had_errors=bool(payload.get("had_errors", False)),
        context_flags=[str(item) for item in payload.get("context_flags", [])],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )


def _action_log_read(row: AutomationActionLog) -> AutomationActionLogRead:
    return AutomationActionLogRead(
        id=row.id,
        organization_id=row.organization_id,
        rule_id=row.rule_id,
        execution_id=row.execution_id,
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


def _get_rule_or_404(db: Session, organization_id: uuid.UUID, rule_id: uuid.UUID) -> AutomationRule:
    rule = db.execute(select(AutomationRule).where(AutomationRule.id == rule_id)).scalar_one_or_none()
    if rule is None or rule.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found")
    return rule


def _get_execution_or_404(db: Session, organization_id: uuid.UUID, execution_id: uuid.UUID) -> AutomationRuleExecution:
    row = db.execute(select(AutomationRuleExecution).where(AutomationRuleExecution.id == execution_id)).scalar_one_or_none()
    if row is None or row.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation execution not found")
    return row


@router.get("/summary", response_model=AutomationSummary)
def automation_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> AutomationSummary:
    return AutomationSummary(**AutomationService(db).summary(organization.id))


@router.get("/schedules/summary", response_model=AutomationScheduleSummary)
def schedule_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> AutomationScheduleSummary:
    return AutomationScheduleSummary(**AutomationService(db).schedule_summary(organization.id))


@router.get("/schedules/due", response_model=list[AutomationRuleRead])
def list_due_scheduled_rules(
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> list[AutomationRuleRead]:
    service = AutomationService(db)
    rows = service.due_scheduled_rules(organization.id, limit=limit)
    return [_rule_read(service.rule_payload(rule=row)) for row in rows]


@router.post("/schedules/run-due", response_model=AutomationScanResponse)
def run_due_scheduled_rules(
    payload: AutomationScanRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:execute")),
) -> AutomationScanResponse:
    service = AutomationService(db)
    executions = service.run_due_scheduled_rules(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        dry_run=payload.dry_run,
        limit=payload.limit,
    )

    AuditService(db).write_audit_log(
        action="automation.scheduled_due_run",
        entity_type="automation_rule",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "execution_count": len(executions),
            "dry_run_requested": payload.dry_run,
            "dry_run_executions": int(sum(1 for item in executions if item.dry_run)),
            "live_executions": int(sum(1 for item in executions if not item.dry_run)),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return AutomationScanResponse(
        execution_count=len(executions),
        executions=[
            AutomationRunResponse(
                execution_id=e.id,
                status=e.status,
                matched_count=e.matched_count,
                action_count=e.action_count,
                skipped_count=e.skipped_count,
                error_count=e.error_count,
                dry_run=e.dry_run,
            )
            for e in executions
        ],
    )


@router.get("/rules", response_model=list[AutomationRuleRead])
def list_rules(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> list[AutomationRuleRead]:
    service = AutomationService(db)
    rows = db.execute(
        select(AutomationRule).where(AutomationRule.organization_id == organization.id).order_by(AutomationRule.created_at.desc())
    ).scalars().all()
    return [_rule_read(service.rule_payload(rule=row)) for row in rows]


@router.post("/rules", response_model=AutomationRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: AutomationRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:write")),
) -> AutomationRuleRead:
    AutomationService.validate_rule_types(payload.condition_type, payload.action_type)

    row = AutomationRule(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        trigger_type=payload.trigger_type,
        condition_type=payload.condition_type,
        condition_config_json=payload.condition_config_json,
        action_type=payload.action_type,
        action_config_json=payload.action_config_json,
        status=payload.status,
        priority=payload.priority,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="automation_rule.created",
        entity_type="automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"name": row.name, "condition_type": row.condition_type, "action_type": row.action_type, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _rule_read(AutomationService(db).rule_payload(rule=row))


@router.get("/rules/{rule_id}", response_model=AutomationRuleRead)
def get_rule_detail(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> AutomationRuleRead:
    row = _get_rule_or_404(db, organization.id, rule_id)
    return _rule_read(AutomationService(db).rule_payload(rule=row))


@router.patch("/rules/{rule_id}", response_model=AutomationRuleRead)
def update_rule(
    rule_id: uuid.UUID,
    payload: AutomationRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:write")),
) -> AutomationRuleRead:
    row = _get_rule_or_404(db, organization.id, rule_id)

    condition_type = payload.condition_type or row.condition_type
    action_type = payload.action_type or row.action_type
    AutomationService.validate_rule_types(condition_type, action_type)

    before = {
        "name": row.name,
        "condition_type": row.condition_type,
        "action_type": row.action_type,
        "status": row.status,
        "priority": row.priority,
    }

    important_changed = False
    for field in [
        "name",
        "description",
        "trigger_type",
        "condition_type",
        "condition_config_json",
        "action_type",
        "action_config_json",
        "status",
        "priority",
    ]:
        value = getattr(payload, field)
        if value is not None and value != getattr(row, field):
            if field in {"trigger_type", "condition_type", "condition_config_json", "action_type", "action_config_json"}:
                important_changed = True
            setattr(row, field, value)

    if important_changed:
        row.version += 1
        AutomationService(db).create_rule_version_snapshot(rule=row, actor_user_id=current_user.id, version_notes=None)

    db.flush()

    AuditService(db).write_audit_log(
        action="automation_rule.updated",
        entity_type="automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "condition_type": row.condition_type,
            "action_type": row.action_type,
            "status": row.status,
            "priority": row.priority,
            "version": row.version,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _rule_read(AutomationService(db).rule_payload(rule=row))


@router.patch("/rules/{rule_id}/schedule", response_model=AutomationRuleRead)
def update_rule_schedule(
    rule_id: uuid.UUID,
    payload: AutomationRuleScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:write")),
) -> AutomationRuleRead:
    row = _get_rule_or_404(db, organization.id, rule_id)
    svc = AutomationService(db)
    if payload.schedule_start_at is not None and payload.schedule_end_at is not None and payload.schedule_end_at < payload.schedule_start_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="schedule_end_at must be greater than or equal to schedule_start_at")
    if (payload.schedule_window_start is None) != (payload.schedule_window_end is None):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="schedule_window_start and schedule_window_end must be set together")

    if payload.schedule_enabled:
        svc.validate_schedule_cadence(payload.schedule_cadence or row.schedule_cadence)
        if row.trigger_type != "scheduled_placeholder":
            row.trigger_type = "scheduled_placeholder"

    before_schedule = {
        "schedule_enabled": row.schedule_enabled,
        "schedule_cadence": row.schedule_cadence,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "version": row.version,
    }

    changed = False
    for field in [
        "schedule_enabled",
        "schedule_cadence",
        "schedule_timezone",
        "schedule_start_at",
        "schedule_end_at",
        "schedule_window_start",
        "schedule_window_end",
        "run_mode",
        "version_notes",
    ]:
        value = getattr(payload, field)
        if value is not None and getattr(row, field) != value:
            setattr(row, field, value)
            changed = True

    if row.schedule_enabled:
        if row.schedule_start_at is not None:
            # First scheduled execution becomes due at schedule_start_at.
            # A past start_at is intentionally treated as due-now.
            row.next_run_at = row.schedule_start_at
        else:
            row.next_run_at = svc.calculate_next_run_at(cadence=row.schedule_cadence, base_time=svc.now())
    else:
        row.next_run_at = None

    if changed:
        row.version += 1
        svc.create_rule_version_snapshot(rule=row, actor_user_id=current_user.id, version_notes=payload.version_notes)

    db.flush()

    AuditService(db).write_audit_log(
        action="automation_rule.schedule_updated",
        entity_type="automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before_schedule,
        after_json={
            "schedule_enabled": row.schedule_enabled,
            "schedule_cadence": row.schedule_cadence,
            "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            "version": row.version,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _rule_read(AutomationService(db).rule_payload(rule=row))


@router.post("/rules/{rule_id}/archive", response_model=AutomationRuleRead)
def archive_rule(
    rule_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:write")),
) -> AutomationRuleRead:
    row = _get_rule_or_404(db, organization.id, rule_id)
    before_status = row.status
    row.status = "archived"
    db.flush()

    AuditService(db).write_audit_log(
        action="automation_rule.archived",
        entity_type="automation_rule",
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
    return _rule_read(AutomationService(db).rule_payload(rule=row))


@router.post("/rules/{rule_id}/run", response_model=AutomationRunResponse)
def run_rule(
    rule_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:execute")),
) -> AutomationRunResponse:
    row = _get_rule_or_404(db, organization.id, rule_id)
    execution = AutomationService(db).run_rule(
        rule=row,
        actor_user_id=current_user.id,
        trigger_source="manual_rule_run",
        dry_run=False,
        allow_scheduled_placeholder=False,
    )

    AuditService(db).write_audit_log(
        action="automation_rule.executed",
        entity_type="automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "execution_id": str(execution.id),
            "status": execution.status,
            "matched_count": execution.matched_count,
            "action_count": execution.action_count,
            "skipped_count": execution.skipped_count,
            "error_count": execution.error_count,
            "dry_run": execution.dry_run,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return AutomationRunResponse(
        execution_id=execution.id,
        status=execution.status,
        matched_count=execution.matched_count,
        action_count=execution.action_count,
        skipped_count=execution.skipped_count,
        error_count=execution.error_count,
        dry_run=execution.dry_run,
    )


@router.post("/rules/{rule_id}/dry-run", response_model=AutomationRunResponse)
def dry_run_rule(
    rule_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:execute")),
) -> AutomationRunResponse:
    row = _get_rule_or_404(db, organization.id, rule_id)
    execution = AutomationService(db).run_rule(
        rule=row,
        actor_user_id=current_user.id,
        trigger_source="dry_run",
        dry_run=True,
        allow_scheduled_placeholder=True,
    )

    AuditService(db).write_audit_log(
        action="automation_rule.dry_run",
        entity_type="automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "execution_id": str(execution.id),
            "status": execution.status,
            "matched_count": execution.matched_count,
            "action_count": execution.action_count,
            "skipped_count": execution.skipped_count,
            "error_count": execution.error_count,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return AutomationRunResponse(
        execution_id=execution.id,
        status=execution.status,
        matched_count=execution.matched_count,
        action_count=execution.action_count,
        skipped_count=execution.skipped_count,
        error_count=execution.error_count,
        dry_run=True,
    )


@router.post("/run-scan", response_model=AutomationScanResponse)
def run_scan(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:execute")),
) -> AutomationScanResponse:
    rules = db.execute(
        select(AutomationRule).where(
            AutomationRule.organization_id == organization.id,
            AutomationRule.status == "active",
            AutomationRule.trigger_type == "manual_scan",
        )
    ).scalars().all()

    service = AutomationService(db)
    results = []
    for rule in rules:
        execution = service.run_rule(
            rule=rule,
            actor_user_id=current_user.id,
            trigger_source="manual_scan",
            dry_run=False,
            allow_scheduled_placeholder=False,
        )
        results.append(
            AutomationRunResponse(
                execution_id=execution.id,
                status=execution.status,
                matched_count=execution.matched_count,
                action_count=execution.action_count,
                skipped_count=execution.skipped_count,
                error_count=execution.error_count,
                dry_run=execution.dry_run,
            )
        )

    AuditService(db).write_audit_log(
        action="automation.scan_executed",
        entity_type="automation_rule",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"execution_count": len(results)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return AutomationScanResponse(execution_count=len(results), executions=results)


@router.get("/rules/{rule_id}/versions", response_model=list[AutomationRuleVersionRead])
def list_rule_versions(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> list[AutomationRuleVersionRead]:
    _get_rule_or_404(db, organization.id, rule_id)
    rows = db.execute(
        select(AutomationRuleVersion)
        .where(
            AutomationRuleVersion.organization_id == organization.id,
            AutomationRuleVersion.rule_id == rule_id,
        )
        .order_by(AutomationRuleVersion.version.desc(), AutomationRuleVersion.created_at.desc())
    ).scalars().all()
    return [_version_read(row) for row in rows]


@router.get("/executions", response_model=list[AutomationExecutionRead])
def list_executions(
    rule_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> list[AutomationExecutionRead]:
    if status_filter is not None:
        status_filter = validate_choice(
            status_filter,
            ("running", "completed", "completed_with_errors"),
            "status",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    stmt = select(AutomationRuleExecution).where(AutomationRuleExecution.organization_id == organization.id)
    if rule_id:
        stmt = stmt.where(AutomationRuleExecution.rule_id == rule_id)
    if status_filter:
        stmt = stmt.where(AutomationRuleExecution.status == status_filter)

    service = AutomationService(db)
    rows = db.execute(stmt.order_by(AutomationRuleExecution.started_at.desc()).offset(offset).limit(limit)).scalars().all()
    return [_execution_read(service.execution_payload(execution=row)) for row in rows]


@router.get("/executions/{execution_id}", response_model=AutomationExecutionDetail)
def get_execution_detail(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("automation:read")),
) -> AutomationExecutionDetail:
    service = AutomationService(db)
    row = _get_execution_or_404(db, organization.id, execution_id)
    action_logs = db.execute(
        select(AutomationActionLog)
        .where(
            AutomationActionLog.organization_id == organization.id,
            AutomationActionLog.execution_id == row.id,
        )
        .order_by(AutomationActionLog.created_at.asc())
    ).scalars().all()

    return AutomationExecutionDetail(
        **_execution_read(service.execution_payload(execution=row)).model_dump(),
        action_logs=[_action_log_read(log) for log in action_logs],
    )
