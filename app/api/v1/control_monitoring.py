import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.control_monitoring_result import ControlMonitoringResult
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.control_monitoring import (
    ControlMonitoringArchiveRequest,
    ControlMonitoringDefinitionCreate,
    ControlMonitoringDefinitionRead,
    ControlMonitoringDefinitionUpdate,
    ControlMonitoringResultRead,
    ControlMonitoringResultRecordRequest,
    ControlMonitoringSummary,
)
from app.services.audit_service import AuditService
from app.services.control_monitoring_service import ControlMonitoringService

router = APIRouter(prefix="/compliance/monitoring", tags=["control-monitoring"])


def _definition_read(row: ControlMonitoringDefinition) -> ControlMonitoringDefinitionRead:
    return ControlMonitoringDefinitionRead(
        id=row.id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        name=row.name,
        description=row.description,
        monitoring_type=row.monitoring_type,
        status=row.status,
        check_frequency=row.check_frequency,
        owner_user_id=row.owner_user_id,
        last_checked_at=row.last_checked_at,
        next_check_due_at=row.next_check_due_at,
        tags_json=row.tags_json,
        notes=row.notes,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        archive_reason=row.archive_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _result_read(row: ControlMonitoringResult) -> ControlMonitoringResultRead:
    return ControlMonitoringResultRead(
        id=row.id,
        organization_id=row.organization_id,
        definition_id=row.definition_id,
        control_id=row.control_id,
        check_status=row.check_status,
        result_summary=row.result_summary,
        result_detail_json=row.result_detail_json,
        checked_by_user_id=row.checked_by_user_id,
        checked_at=row.checked_at,
        next_check_due_at=row.next_check_due_at,
        created_at=row.created_at,
    )


@router.post("/definitions", response_model=ControlMonitoringDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_monitoring_definition(
    payload: ControlMonitoringDefinitionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringDefinitionRead:
    service = ControlMonitoringService(db)
    service.require_control_in_org(organization.id, payload.control_id)
    service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)

    row = ControlMonitoringDefinition(
        organization_id=organization.id,
        control_id=payload.control_id,
        name=payload.name,
        description=payload.description,
        monitoring_type=payload.monitoring_type,
        status="active",
        check_frequency=payload.check_frequency,
        owner_user_id=payload.owner_user_id,
        tags_json=payload.tags_json,
        notes=payload.notes,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_definition.created",
        entity_type="control_monitoring_definition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "control_id": str(row.control_id),
            "name": row.name,
            "monitoring_type": row.monitoring_type,
            "status": row.status,
            "check_frequency": row.check_frequency,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _definition_read(row)


@router.get("/definitions", response_model=list[ControlMonitoringDefinitionRead])
def list_monitoring_definitions(
    status_filter: str | None = Query(default=None, alias="status"),
    monitoring_type: str | None = Query(default=None),
    control_id: uuid.UUID | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None, alias="owner"),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> list[ControlMonitoringDefinitionRead]:
    stmt = select(ControlMonitoringDefinition).where(ControlMonitoringDefinition.organization_id == organization.id)
    if status_filter is not None:
        stmt = stmt.where(ControlMonitoringDefinition.status == status_filter)
    if monitoring_type is not None:
        stmt = stmt.where(ControlMonitoringDefinition.monitoring_type == monitoring_type)
    if control_id is not None:
        stmt = stmt.where(ControlMonitoringDefinition.control_id == control_id)
    if owner_user_id is not None:
        stmt = stmt.where(ControlMonitoringDefinition.owner_user_id == owner_user_id)
    if not include_archived:
        stmt = stmt.where(ControlMonitoringDefinition.status != "archived")

    rows = db.execute(stmt.order_by(ControlMonitoringDefinition.created_at.desc())).scalars().all()
    return [_definition_read(row) for row in rows]


@router.get("/definitions/{definition_id}", response_model=ControlMonitoringDefinitionRead)
def get_monitoring_definition(
    definition_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringDefinitionRead:
    row = ControlMonitoringService(db).require_definition_in_org(organization.id, definition_id)
    return _definition_read(row)


@router.patch("/definitions/{definition_id}", response_model=ControlMonitoringDefinitionRead)
def update_monitoring_definition(
    definition_id: uuid.UUID,
    payload: ControlMonitoringDefinitionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringDefinitionRead:
    service = ControlMonitoringService(db)
    row = service.require_definition_in_org(organization.id, definition_id)
    changes = payload.model_dump(exclude_unset=True)

    if row.status == "archived":
        disallowed = sorted([field for field in changes if field not in {"notes", "tags_json"}])
        if disallowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived monitoring definitions can only update notes and tags_json",
            )

    if "control_id" in changes:
        service.require_control_in_org(organization.id, changes["control_id"])
    if "owner_user_id" in changes and changes["owner_user_id"] is not None:
        service.ensure_owner_is_active_member(organization.id, changes["owner_user_id"])

    before = {
        "name": row.name,
        "monitoring_type": row.monitoring_type,
        "status": row.status,
        "check_frequency": row.check_frequency,
        "owner_user_id": str(row.owner_user_id),
    }
    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_definition.updated",
        entity_type="control_monitoring_definition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "monitoring_type": row.monitoring_type,
            "status": row.status,
            "check_frequency": row.check_frequency,
            "owner_user_id": str(row.owner_user_id),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _definition_read(row)


@router.post("/definitions/{definition_id}/archive", response_model=ControlMonitoringDefinitionRead)
def archive_monitoring_definition(
    definition_id: uuid.UUID,
    payload: ControlMonitoringArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringDefinitionRead:
    service = ControlMonitoringService(db)
    row = service.require_definition_in_org(organization.id, definition_id)

    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monitoring definition is already archived")

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
        action="control_monitoring_definition.archived",
        entity_type="control_monitoring_definition",
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
    return _definition_read(row)


@router.post("/definitions/{definition_id}/activate", response_model=ControlMonitoringDefinitionRead)
def activate_monitoring_definition(
    definition_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringDefinitionRead:
    row = ControlMonitoringService(db).require_definition_in_org(organization.id, definition_id)
    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived monitoring definitions cannot be activated")
    if row.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monitoring definition is already active")

    row.status = "active"
    db.commit()
    db.refresh(row)
    return _definition_read(row)


@router.post("/definitions/{definition_id}/deactivate", response_model=ControlMonitoringDefinitionRead)
def deactivate_monitoring_definition(
    definition_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringDefinitionRead:
    row = ControlMonitoringService(db).require_definition_in_org(organization.id, definition_id)
    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived monitoring definitions cannot be deactivated")
    if row.status == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monitoring definition is already inactive")

    row.status = "inactive"
    db.commit()
    db.refresh(row)
    return _definition_read(row)


@router.post("/definitions/{definition_id}/record-result", response_model=ControlMonitoringResultRead, status_code=status.HTTP_201_CREATED)
def record_monitoring_result(
    definition_id: uuid.UUID,
    payload: ControlMonitoringResultRecordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:write")),
) -> ControlMonitoringResultRead:
    service = ControlMonitoringService(db)
    definition = service.require_definition_in_org(organization.id, definition_id)
    if definition.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived monitoring definitions cannot accept new results")

    checked_at = service.utcnow()
    next_due = service.compute_next_check_due_at(definition.check_frequency, checked_at)

    row = ControlMonitoringResult(
        organization_id=organization.id,
        definition_id=definition.id,
        control_id=definition.control_id,
        check_status=payload.check_status,
        result_summary=payload.result_summary,
        result_detail_json=payload.result_detail_json,
        checked_by_user_id=current_user.id,
        checked_at=checked_at,
        next_check_due_at=next_due,
    )
    db.add(row)

    definition.last_checked_at = checked_at
    definition.next_check_due_at = next_due
    db.flush()

    AuditService(db).write_audit_log(
        action="control_monitoring_result.recorded",
        entity_type="control_monitoring_result",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "definition_id": str(definition.id),
            "control_id": str(definition.control_id),
            "check_status": row.check_status,
            "checked_at": row.checked_at.isoformat(),
            "next_check_due_at": row.next_check_due_at.isoformat() if row.next_check_due_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _result_read(row)


@router.get("/definitions/{definition_id}/results", response_model=list[ControlMonitoringResultRead])
def list_definition_results(
    definition_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> list[ControlMonitoringResultRead]:
    service = ControlMonitoringService(db)
    _ = service.require_definition_in_org(organization.id, definition_id)

    rows = db.execute(
        select(ControlMonitoringResult)
        .where(
            ControlMonitoringResult.organization_id == organization.id,
            ControlMonitoringResult.definition_id == definition_id,
        )
        .order_by(ControlMonitoringResult.checked_at.desc(), ControlMonitoringResult.id.desc())
    ).scalars().all()
    return [_result_read(row) for row in rows]


@router.get("/results", response_model=list[ControlMonitoringResultRead])
def list_org_monitoring_results(
    definition_id: uuid.UUID | None = Query(default=None),
    control_id: uuid.UUID | None = Query(default=None),
    check_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> list[ControlMonitoringResultRead]:
    stmt = select(ControlMonitoringResult).where(ControlMonitoringResult.organization_id == organization.id)
    if definition_id is not None:
        stmt = stmt.where(ControlMonitoringResult.definition_id == definition_id)
    if control_id is not None:
        stmt = stmt.where(ControlMonitoringResult.control_id == control_id)
    if check_status is not None:
        stmt = stmt.where(ControlMonitoringResult.check_status == check_status)

    rows = db.execute(stmt.order_by(ControlMonitoringResult.checked_at.desc(), ControlMonitoringResult.id.desc())).scalars().all()
    return [_result_read(row) for row in rows]


@router.get("/summary", response_model=ControlMonitoringSummary)
def monitoring_summary(
    include_inactive: bool = Query(default=False),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("monitoring:read")),
) -> ControlMonitoringSummary:
    return ControlMonitoringSummary(
        **ControlMonitoringService(db).summary(
            organization.id,
            include_inactive=include_inactive,
            include_archived=include_archived,
        )
    )
