import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control import Control
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.repositories.control_test_repository import ControlTestRepository
from app.schemas.control_test import (
    ControlTestDefinitionCreate,
    ControlTestDefinitionRead,
    ControlTestDefinitionUpdate,
    ControlTestingSummary,
    ControlTestRunCreateRequest,
    ControlTestRunRead,
    ControlTestRunResponse,
)
from app.services.audit_service import AuditService
from app.services.control_test_service import ALLOWED_RESULTS, ControlTestService
from app.core.validation import validate_choice

router = APIRouter(tags=["control-tests"])


def _to_definition_read(row: ControlTestDefinition) -> ControlTestDefinitionRead:
    now = ControlTestService.now()
    next_due_at = ControlTestService._to_utc(row.next_due_at)
    is_overdue = row.status == "active" and next_due_at is not None and next_due_at < now
    return ControlTestDefinitionRead(
        id=row.id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        name=row.name,
        description=row.description,
        test_type=row.test_type,
        check_key=row.check_key,
        status=row.status,
        cadence=row.cadence,
        next_due_at=row.next_due_at,
        last_run_at=row.last_run_at,
        owner_user_id=row.owner_user_id,
        created_by_user_id=row.created_by_user_id,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_overdue=is_overdue,
    )


def _to_run_read(row: ControlTestRun) -> ControlTestRunRead:
    return ControlTestRunRead(
        id=row.id,
        organization_id=row.organization_id,
        control_test_definition_id=row.control_test_definition_id,
        control_id=row.control_id,
        result=row.result,
        result_reason=row.result_reason,
        check_key=row.check_key,
        executed_by_user_id=row.executed_by_user_id,
        execution_source=row.execution_source,
        evidence_item_id=row.evidence_item_id,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


def _require_definition(db: Session, organization_id: uuid.UUID, test_id: uuid.UUID) -> ControlTestDefinition:
    row = ControlTestRepository(db).get_definition_by_id(test_id)
    if row is None or row.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control test definition not found")
    return row


@router.post("/controls/{control_id}/tests", response_model=ControlTestDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_control_test_definition(
    control_id: uuid.UUID,
    payload: ControlTestDefinitionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlTestDefinitionRead:
    service = ControlTestService(db)
    control = service.require_control_in_org(organization.id, control_id)
    service.validate_test_type_and_check_key(payload.test_type, payload.check_key)
    service.validate_cadence(payload.cadence)
    service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)

    row = ControlTestDefinition(
        organization_id=organization.id,
        control_id=control.id,
        name=payload.name,
        description=payload.description,
        test_type=payload.test_type,
        check_key=payload.check_key,
        status="active",
        cadence=payload.cadence,
        next_due_at=payload.next_due_at,
        owner_user_id=payload.owner_user_id,
        created_by_user_id=current_user.id,
        metadata_json=payload.metadata_json,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="control_test.created",
        entity_type="control_test_definition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "control_id": str(control.id),
            "name": row.name,
            "test_type": row.test_type,
            "check_key": row.check_key,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _to_definition_read(row)


@router.get("/controls/{control_id}/tests", response_model=list[ControlTestDefinitionRead])
def list_control_test_definitions(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[ControlTestDefinitionRead]:
    ControlTestService(db).require_control_in_org(organization.id, control_id)
    rows = ControlTestRepository(db).list_definitions_for_control(organization.id, control_id)
    return [_to_definition_read(row) for row in rows]


@router.patch("/control-tests/{test_id}", response_model=ControlTestDefinitionRead)
def update_control_test_definition(
    test_id: uuid.UUID,
    payload: ControlTestDefinitionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlTestDefinitionRead:
    row = _require_definition(db, organization.id, test_id)
    service = ControlTestService(db)

    if payload.cadence is not None:
        service.validate_cadence(payload.cadence)
    if payload.owner_user_id is not None:
        service.ensure_owner_is_active_member(organization.id, payload.owner_user_id)

    before = {
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "cadence": row.cadence,
        "next_due_at": row.next_due_at.isoformat() if row.next_due_at else None,
        "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
    }

    for field in ["name", "description", "status", "cadence", "next_due_at", "owner_user_id", "metadata_json"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)

    db.flush()

    AuditService(db).write_audit_log(
        action="control_test.updated",
        entity_type="control_test_definition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "cadence": row.cadence,
            "next_due_at": row.next_due_at.isoformat() if row.next_due_at else None,
            "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _to_definition_read(row)


@router.post("/control-tests/{test_id}/archive", response_model=ControlTestDefinitionRead)
def archive_control_test_definition(
    test_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlTestDefinitionRead:
    row = _require_definition(db, organization.id, test_id)
    before_status = row.status
    row.status = "archived"
    db.flush()

    AuditService(db).write_audit_log(
        action="control_test.archived",
        entity_type="control_test_definition",
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
    return _to_definition_read(row)


@router.post("/control-tests/{test_id}/run", response_model=ControlTestRunResponse)
def run_control_test(
    test_id: uuid.UUID,
    payload: ControlTestRunCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlTestRunResponse:
    definition = _require_definition(db, organization.id, test_id)
    service = ControlTestService(db)
    control = service.require_control_in_org(organization.id, definition.control_id)
    service.require_evidence_in_org(organization.id, payload.evidence_item_id)

    if definition.test_type == "manual_attestation":
        if payload.manual_result is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="manual_result is required for manual_attestation")
        payload.manual_result = validate_choice(payload.manual_result, ALLOWED_RESULTS, "manual_result", status_code=status.HTTP_400_BAD_REQUEST)
        result = payload.manual_result
        result_reason = payload.result_reason or "Manual attestation result"
    else:
        result, default_reason = service.evaluate_internal_check(
            organization_id=organization.id,
            control=control,
            check_key=definition.check_key,
            evidence_item_id=payload.evidence_item_id,
        )
        result_reason = payload.result_reason or default_reason

    if payload.dry_run:
        return ControlTestRunResponse(
            dry_run=True,
            run=None,
            computed_result=result,
            computed_reason=result_reason,
        )

    run = ControlTestRun(
        organization_id=organization.id,
        control_test_definition_id=definition.id,
        control_id=control.id,
        result=result,
        result_reason=result_reason,
        check_key=definition.check_key,
        executed_by_user_id=current_user.id,
        execution_source="manual",
        evidence_item_id=payload.evidence_item_id,
        metadata_json={"test_type": definition.test_type, "dry_run": False},
        created_at=service.now(),
    )
    db.add(run)

    definition.last_run_at = run.created_at
    definition.next_due_at = service.calculate_next_due_at(definition.cadence, from_time=run.created_at)

    db.flush()

    AuditService(db).write_audit_log(
        action="control_test.run_created",
        entity_type="control_test_run",
        entity_id=run.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "control_test_definition_id": str(definition.id),
            "control_id": str(control.id),
            "result": run.result,
            "check_key": run.check_key,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(run)
    return ControlTestRunResponse(
        dry_run=False,
        run=_to_run_read(run),
        computed_result=result,
        computed_reason=result_reason,
    )


@router.get("/controls/{control_id}/test-runs", response_model=list[ControlTestRunRead])
def list_control_test_runs(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[ControlTestRunRead]:
    ControlTestService(db).require_control_in_org(organization.id, control_id)
    rows = ControlTestRepository(db).list_runs_for_control(organization.id, control_id)
    return [_to_run_read(row) for row in rows]


@router.get("/control-tests/summary", response_model=ControlTestingSummary)
def control_testing_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlTestingSummary:
    return ControlTestingSummary(**ControlTestService(db).run_summary(organization.id))
