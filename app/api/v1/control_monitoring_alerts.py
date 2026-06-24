import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.control_monitoring_alert import (
    ControlMonitoringAlertAssignRequest,
    ControlMonitoringAlertCreate,
    ControlMonitoringAlertDismissRequest,
    ControlMonitoringAlertRead,
    ControlMonitoringAlertResolveRequest,
    ControlMonitoringAlertSummary,
)
from app.services.audit_service import AuditService
from app.services.control_monitoring_alert_service import ControlMonitoringAlertService

router = APIRouter(prefix="/compliance/monitoring/alerts", tags=["control-monitoring-alerts"])


def _alert_read(row: ControlMonitoringAlert) -> ControlMonitoringAlertRead:
    return ControlMonitoringAlertRead(
        id=row.id,
        organization_id=row.organization_id,
        rule_id=row.rule_id,
        definition_id=row.definition_id,
        control_id=row.control_id,
        alert_type=row.alert_type,
        severity=row.severity,
        status=row.status,
        title=row.title,
        description=row.description,
        alert_context_json=row.alert_context_json,
        assigned_to_user_id=row.assigned_to_user_id,
        acknowledged_at=row.acknowledged_at,
        acknowledged_by_user_id=row.acknowledged_by_user_id,
        resolved_at=row.resolved_at,
        resolved_by_user_id=row.resolved_by_user_id,
        resolution_notes=row.resolution_notes,
        dismissed_at=row.dismissed_at,
        dismissed_by_user_id=row.dismissed_by_user_id,
        dismissal_reason=row.dismissal_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=ControlMonitoringAlertRead, status_code=status.HTTP_201_CREATED)
def create_manual_alert(
    payload: ControlMonitoringAlertCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringAlertRead:
    service = ControlMonitoringAlertService(db)

    if payload.rule_id is not None:
        service.require_rule_in_org(organization.id, payload.rule_id)
    if payload.definition_id is not None:
        service.require_definition_in_org(organization.id, payload.definition_id)
    if payload.control_id is not None:
        service.require_control_in_org(organization.id, payload.control_id)
    if payload.assigned_to_user_id is not None:
        service.ensure_active_member(organization.id, payload.assigned_to_user_id, field_name="assigned_to_user_id")

    row = ControlMonitoringAlert(
        organization_id=organization.id,
        rule_id=payload.rule_id,
        definition_id=payload.definition_id,
        control_id=payload.control_id,
        alert_type="manual",
        severity=payload.severity,
        status="open",
        title=payload.title,
        description=payload.description,
        alert_context_json=payload.alert_context_json,
        assigned_to_user_id=payload.assigned_to_user_id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_alert.created",
        entity_type="control_monitoring_alert",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "alert_type": row.alert_type,
            "severity": row.severity,
            "status": row.status,
            "title": row.title,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _alert_read(row)


@router.get("/summary", response_model=ControlMonitoringAlertSummary)
def monitoring_alert_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringAlertSummary:
    return ControlMonitoringAlertSummary(**ControlMonitoringAlertService(db).summary(organization.id))


@router.get("", response_model=list[ControlMonitoringAlertRead])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    rule_id: uuid.UUID | None = Query(default=None),
    definition_id: uuid.UUID | None = Query(default=None),
    control_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> list[ControlMonitoringAlertRead]:
    stmt = select(ControlMonitoringAlert).where(ControlMonitoringAlert.organization_id == organization.id)
    if status_filter is not None:
        stmt = stmt.where(ControlMonitoringAlert.status == status_filter)
    if severity is not None:
        stmt = stmt.where(ControlMonitoringAlert.severity == severity)
    if alert_type is not None:
        stmt = stmt.where(ControlMonitoringAlert.alert_type == alert_type)
    if assigned_to is not None:
        stmt = stmt.where(ControlMonitoringAlert.assigned_to_user_id == assigned_to)
    if rule_id is not None:
        stmt = stmt.where(ControlMonitoringAlert.rule_id == rule_id)
    if definition_id is not None:
        stmt = stmt.where(ControlMonitoringAlert.definition_id == definition_id)
    if control_id is not None:
        stmt = stmt.where(ControlMonitoringAlert.control_id == control_id)

    rows = db.execute(stmt.order_by(ControlMonitoringAlert.created_at.desc())).scalars().all()
    return [_alert_read(row) for row in rows]


@router.get("/{alert_id}", response_model=ControlMonitoringAlertRead)
def get_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringAlertRead:
    row = ControlMonitoringAlertService(db).require_alert_in_org(organization.id, alert_id)
    return _alert_read(row)


@router.post("/{alert_id}/acknowledge", response_model=ControlMonitoringAlertRead)
def acknowledge_alert(
    alert_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringAlertRead:
    service = ControlMonitoringAlertService(db)
    row = service.require_alert_in_org(organization.id, alert_id)

    if row.status != "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open alerts can be acknowledged")

    row.status = "acknowledged"
    row.acknowledged_at = service.utcnow()
    row.acknowledged_by_user_id = current_user.id
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_alert.acknowledged",
        entity_type="control_monitoring_alert",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "acknowledged_at": row.acknowledged_at.isoformat()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _alert_read(row)


@router.post("/{alert_id}/resolve", response_model=ControlMonitoringAlertRead)
def resolve_alert(
    alert_id: uuid.UUID,
    payload: ControlMonitoringAlertResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringAlertRead:
    service = ControlMonitoringAlertService(db)
    row = service.require_alert_in_org(organization.id, alert_id)

    if row.status == "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Open alerts must be acknowledged before resolve")
    if row.status != "acknowledged":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only acknowledged alerts can be resolved")

    row.status = "resolved"
    row.resolved_at = service.utcnow()
    row.resolved_by_user_id = current_user.id
    row.resolution_notes = payload.resolution_notes
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_alert.resolved",
        entity_type="control_monitoring_alert",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "resolved_at": row.resolved_at.isoformat()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _alert_read(row)


@router.post("/{alert_id}/dismiss", response_model=ControlMonitoringAlertRead)
def dismiss_alert(
    alert_id: uuid.UUID,
    payload: ControlMonitoringAlertDismissRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringAlertRead:
    service = ControlMonitoringAlertService(db)
    row = service.require_alert_in_org(organization.id, alert_id)

    if row.status not in {"open", "acknowledged"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open or acknowledged alerts can be dismissed")

    row.status = "dismissed"
    row.dismissed_at = service.utcnow()
    row.dismissed_by_user_id = current_user.id
    row.dismissal_reason = payload.dismissal_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_alert.dismissed",
        entity_type="control_monitoring_alert",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "dismissed_at": row.dismissed_at.isoformat()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _alert_read(row)


@router.post("/{alert_id}/assign", response_model=ControlMonitoringAlertRead)
def assign_alert(
    alert_id: uuid.UUID,
    payload: ControlMonitoringAlertAssignRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringAlertRead:
    service = ControlMonitoringAlertService(db)
    row = service.require_alert_in_org(organization.id, alert_id)
    service.ensure_not_terminal(row)

    if payload.assigned_to_user_id is not None:
        service.ensure_active_member(organization.id, payload.assigned_to_user_id, field_name="assigned_to_user_id")

    row.assigned_to_user_id = payload.assigned_to_user_id
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_alert.assigned",
        entity_type="control_monitoring_alert",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"assigned_to_user_id": str(payload.assigned_to_user_id) if payload.assigned_to_user_id else None},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _alert_read(row)
