import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.dora_service import DORAService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.dora_ict_register import DORAICTRegister
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.dora import DORAICTRegisterCreate, DORAICTRegisterRead, DORAICTRegisterReportRead, DORAICTRegisterUpdate

router = APIRouter(prefix="/compliance/dora", tags=["dora"])


def _read(row: DORAICTRegister) -> DORAICTRegisterRead:
    return DORAICTRegisterRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        counterparty_name=row.counterparty_name,
        service_description=row.service_description,
        is_critical_function=row.is_critical_function,
        sub_outsourcing_used=row.sub_outsourcing_used,
        data_location=row.data_location,
        data_location_countries=row.data_location_countries,
        contract_start_date=row.contract_start_date,
        contract_end_date=row.contract_end_date,
        exit_strategy_documented=row.exit_strategy_documented,
        exit_strategy_notes=row.exit_strategy_notes,
        last_assessed_at=row.last_assessed_at,
        assessment_frequency=row.assessment_frequency,
        dora_article=row.dora_article,
        status=row.status,
        owner_id=row.owner_id,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


@router.post("/ict-register", response_model=DORAICTRegisterRead, status_code=status.HTTP_201_CREATED)
def create_ict_register_entry(
    payload: DORAICTRegisterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> DORAICTRegisterRead:
    row = DORAService(db).create_ict_register_entry(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("/ict-register", response_model=list[DORAICTRegisterRead])
def list_ict_register(
    is_critical: bool | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[DORAICTRegisterRead]:
    rows = DORAService(db).list_ict_register(organization.id, is_critical=is_critical, status_value=status_value)
    return [_read(row) for row in rows]


@router.get("/ict-register/report", response_model=DORAICTRegisterReportRead)
def get_ict_register_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> DORAICTRegisterReportRead:
    return DORAICTRegisterReportRead.model_validate(DORAService(db).get_ict_register_report(organization.id))


@router.get("/ict-register/{entry_id}", response_model=DORAICTRegisterRead)
def get_ict_register_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> DORAICTRegisterRead:
    row = DORAService(db).get_ict_entry(organization.id, entry_id)
    return _read(row)


@router.patch("/ict-register/{entry_id}", response_model=DORAICTRegisterRead)
def update_ict_register_entry(
    entry_id: uuid.UUID,
    payload: DORAICTRegisterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> DORAICTRegisterRead:
    row = DORAService(db).update_ict_entry(organization.id, entry_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.delete("/ict-register/{entry_id}", response_model=DORAICTRegisterRead)
def soft_delete_ict_register_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> DORAICTRegisterRead:
    row = DORAService(db).soft_delete_ict_entry(organization.id, entry_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)
