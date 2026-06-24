import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control_monitoring_rule import ControlMonitoringRule
from app.models.control_monitoring_rule_execution import ControlMonitoringRuleExecution
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.control_monitoring_rule import (
    ControlMonitoringRuleArchiveRequest,
    ControlMonitoringRuleCreate,
    ControlMonitoringRuleEvaluateRequest,
    ControlMonitoringRuleEvaluateResponse,
    ControlMonitoringRuleExecutionRead,
    ControlMonitoringRuleRead,
    ControlMonitoringRuleSummary,
    ControlMonitoringRuleUpdate,
)
from app.services.audit_service import AuditService
from app.services.control_monitoring_rule_service import ControlMonitoringRuleService

router = APIRouter(prefix="/compliance/monitoring/rules", tags=["control-monitoring-rules"])


def _rule_read(row: ControlMonitoringRule) -> ControlMonitoringRuleRead:
    scope_ids = None
    if isinstance(row.scope_definition_ids, list):
        scope_ids = [uuid.UUID(str(v)) for v in row.scope_definition_ids]

    return ControlMonitoringRuleRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        rule_type=row.rule_type,
        condition_json=dict(row.condition_json),
        action_type=row.action_type,
        action_config_json=dict(row.action_config_json),
        scope_definition_ids=scope_ids,
        last_evaluated_at=row.last_evaluated_at,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        archive_reason=row.archive_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _execution_read(row: ControlMonitoringRuleExecution) -> ControlMonitoringRuleExecutionRead:
    return ControlMonitoringRuleExecutionRead(
        id=row.id,
        organization_id=row.organization_id,
        rule_id=row.rule_id,
        triggered_at=row.triggered_at,
        dry_run=row.dry_run,
        matched_count=row.matched_count,
        action_count=row.action_count,
        skipped_count=row.skipped_count,
        execution_summary_json=dict(row.execution_summary_json),
        created_at=row.created_at,
    )


@router.post("", response_model=ControlMonitoringRuleRead, status_code=status.HTTP_201_CREATED)
def create_monitoring_rule(
    payload: ControlMonitoringRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringRuleRead:
    service = ControlMonitoringRuleService(db)
    condition_json = service.validate_condition_json(payload.rule_type, payload.condition_json)
    scope_ids = service.validate_scope_definition_ids(organization.id, payload.scope_definition_ids)

    row = ControlMonitoringRule(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        status="active",
        rule_type=payload.rule_type,
        condition_json=condition_json,
        action_type=payload.action_type,
        action_config_json=payload.action_config_json,
        scope_definition_ids=[str(v) for v in scope_ids] if scope_ids else None,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_rule.created",
        entity_type="control_monitoring_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "rule_type": row.rule_type,
            "action_type": row.action_type,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.get("", response_model=list[ControlMonitoringRuleRead])
def list_monitoring_rules(
    status_filter: str | None = Query(default=None, alias="status"),
    rule_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> list[ControlMonitoringRuleRead]:
    stmt = select(ControlMonitoringRule).where(ControlMonitoringRule.organization_id == organization.id)
    if status_filter is not None:
        stmt = stmt.where(ControlMonitoringRule.status == status_filter)
    if rule_type is not None:
        stmt = stmt.where(ControlMonitoringRule.rule_type == rule_type)
    if not include_archived:
        stmt = stmt.where(ControlMonitoringRule.status != "archived")
    rows = db.execute(stmt.order_by(ControlMonitoringRule.created_at.desc())).scalars().all()
    return [_rule_read(row) for row in rows]


@router.post("/evaluate", response_model=ControlMonitoringRuleEvaluateResponse)
def evaluate_monitoring_rules(
    payload: ControlMonitoringRuleEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringRuleEvaluateResponse:
    service = ControlMonitoringRuleService(db)
    active_rules = db.execute(
        select(ControlMonitoringRule).where(
            ControlMonitoringRule.organization_id == organization.id,
            ControlMonitoringRule.status == "active",
        )
        .order_by(ControlMonitoringRule.created_at.asc())
    ).scalars().all()

    executions: list[ControlMonitoringRuleExecution] = []
    for rule in active_rules:
        execution = service.evaluate_rule(
            organization_id=organization.id,
            rule=rule,
            actor_user_id=current_user.id,
            dry_run=payload.dry_run,
        )
        executions.append(execution)

        AuditService(db).write_audit_log(
            action="control_monitoring_rule.evaluated",
            entity_type="control_monitoring_rule",
            entity_id=rule.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "dry_run": payload.dry_run,
                "execution_id": str(execution.id),
                "matched_count": execution.matched_count,
                "action_count": execution.action_count,
                "skipped_count": execution.skipped_count,
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    db.commit()

    for execution in executions:
        db.refresh(execution)

    return ControlMonitoringRuleEvaluateResponse(
        dry_run=payload.dry_run,
        evaluated_rules=len(active_rules),
        executions=[_execution_read(execution) for execution in executions],
    )


@router.get("/executions", response_model=list[ControlMonitoringRuleExecutionRead])
def list_monitoring_rule_executions(
    rule_id: uuid.UUID | None = Query(default=None),
    dry_run: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> list[ControlMonitoringRuleExecutionRead]:
    stmt = select(ControlMonitoringRuleExecution).where(ControlMonitoringRuleExecution.organization_id == organization.id)
    if rule_id is not None:
        stmt = stmt.where(ControlMonitoringRuleExecution.rule_id == rule_id)
    if dry_run is not None:
        stmt = stmt.where(ControlMonitoringRuleExecution.dry_run == dry_run)

    rows = db.execute(stmt.order_by(ControlMonitoringRuleExecution.triggered_at.desc())).scalars().all()
    return [_execution_read(row) for row in rows]


@router.get("/executions/{execution_id}", response_model=ControlMonitoringRuleExecutionRead)
def get_monitoring_rule_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringRuleExecutionRead:
    row = ControlMonitoringRuleService(db).require_execution_in_org(organization.id, execution_id)
    return _execution_read(row)


@router.get("/summary", response_model=ControlMonitoringRuleSummary)
def monitoring_rule_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringRuleSummary:
    return ControlMonitoringRuleSummary(**ControlMonitoringRuleService(db).summary(organization.id))


@router.get("/{rule_id}", response_model=ControlMonitoringRuleRead)
def get_monitoring_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringRuleRead:
    row = ControlMonitoringRuleService(db).require_rule_in_org(organization.id, rule_id)
    return _rule_read(row)


@router.patch("/{rule_id}", response_model=ControlMonitoringRuleRead)
def update_monitoring_rule(
    rule_id: uuid.UUID,
    payload: ControlMonitoringRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringRuleRead:
    service = ControlMonitoringRuleService(db)
    row = service.require_rule_in_org(organization.id, rule_id)
    changes = payload.model_dump(exclude_unset=True)

    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived monitoring rules cannot be updated")

    new_rule_type = changes.get("rule_type", row.rule_type)
    if "condition_json" in changes or "rule_type" in changes:
        new_condition = changes.get("condition_json", dict(row.condition_json))
        changes["condition_json"] = service.validate_condition_json(new_rule_type, new_condition)

    if "scope_definition_ids" in changes:
        scope_ids = service.validate_scope_definition_ids(organization.id, changes["scope_definition_ids"])
        changes["scope_definition_ids"] = [str(v) for v in scope_ids] if scope_ids else None

    before = {
        "name": row.name,
        "status": row.status,
        "rule_type": row.rule_type,
        "action_type": row.action_type,
    }

    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_rule.updated",
        entity_type="control_monitoring_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "rule_type": row.rule_type,
            "action_type": row.action_type,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.post("/{rule_id}/archive", response_model=ControlMonitoringRuleRead)
def archive_monitoring_rule(
    rule_id: uuid.UUID,
    payload: ControlMonitoringRuleArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringRuleRead:
    service = ControlMonitoringRuleService(db)
    row = service.require_rule_in_org(organization.id, rule_id)

    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monitoring rule is already archived")

    before = {
        "status": row.status,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archive_reason": row.archive_reason,
    }

    row.status = "archived"
    row.archived_at = service.utcnow()
    row.archived_by_user_id = current_user.id
    row.archive_reason = payload.reason
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_rule.archived",
        entity_type="control_monitoring_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archive_reason": row.archive_reason,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.post("/{rule_id}/activate", response_model=ControlMonitoringRuleRead)
def activate_monitoring_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringRuleRead:
    row = ControlMonitoringRuleService(db).require_rule_in_org(organization.id, rule_id)
    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived monitoring rules cannot be activated")
    if row.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monitoring rule is already active")
    row.status = "active"
    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.post("/{rule_id}/deactivate", response_model=ControlMonitoringRuleRead)
def deactivate_monitoring_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringRuleRead:
    row = ControlMonitoringRuleService(db).require_rule_in_org(organization.id, rule_id)
    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived monitoring rules cannot be deactivated")
    if row.status == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monitoring rule is already inactive")
    row.status = "inactive"
    db.commit()
    db.refresh(row)
    return _rule_read(row)
