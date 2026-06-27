import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.offboarding_service import OffboardingService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_org_membership
from app.models.membership import Membership
from app.models.offboarding_configuration import OffboardingConfiguration
from app.models.offboarding_record import OffboardingRecord
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.schemas.offboarding import (
    OffboardingConfigurationRead,
    OffboardingConfigurationUpdate,
    OffboardingRecordRead,
    OffboardingRunRequest,
    OffboardingValidationRead,
)

router = APIRouter(prefix="/compliance/offboarding", tags=["offboarding"])


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _config_read(row: OffboardingConfiguration) -> OffboardingConfigurationRead:
    return OffboardingConfigurationRead(
        id=row.id,
        organization_id=row.organization_id,
        default_successor_id=row.default_successor_id,
        require_successor_on_deactivate=row.require_successor_on_deactivate,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _record_read(row: OffboardingRecord) -> OffboardingRecordRead:
    return OffboardingRecordRead(
        id=row.id,
        organization_id=row.organization_id,
        deactivated_user_id=row.deactivated_user_id,
        successor_id=row.successor_id,
        records_reassigned=dict(row.records_reassigned or {}),
        total_reassigned=row.total_reassigned,
        executed_by=row.executed_by,
        executed_at=row.executed_at,
    )


@router.get("/configuration", response_model=OffboardingConfigurationRead)
def get_configuration(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> OffboardingConfigurationRead:
    _require_org_admin(db, membership)
    row = OffboardingService(db).get_or_create_config(organization.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)


@router.patch("/configuration", response_model=OffboardingConfigurationRead)
def update_configuration(
    payload: OffboardingConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> OffboardingConfigurationRead:
    _require_org_admin(db, membership)
    row = OffboardingService(db).update_config(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)


@router.post("/validate/{user_id}", response_model=OffboardingValidationRead)
def validate_offboarding(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> OffboardingValidationRead:
    _require_org_admin(db, membership)
    payload = OffboardingService(db).validate_offboarding(organization.id, user_id)
    from app.services.audit_service import AuditService

    AuditService(db).write_audit_log(
        action="offboarding.validated",
        entity_type="offboarding",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"deactivated_user_id": str(user_id), **payload},
        metadata_json={"source": "api"},
    )
    db.commit()
    return OffboardingValidationRead(**payload)


@router.post("/run", response_model=OffboardingRecordRead)
def run_offboarding(
    payload: OffboardingRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> OffboardingRecordRead:
    _require_org_admin(db, membership)
    row = OffboardingService(db).run_offboarding(
        organization.id,
        payload.deactivated_user_id,
        payload.successor_id,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _record_read(row)


@router.get("/records", response_model=list[OffboardingRecordRead])
def list_records(
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> list[OffboardingRecordRead]:
    _require_org_admin(db, membership)
    rows = OffboardingService(db).get_offboarding_records(organization.id, user_id=user_id)
    return [_record_read(row) for row in rows]


@router.get("/records/{record_id}", response_model=OffboardingRecordRead)
def get_record(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> OffboardingRecordRead:
    _require_org_admin(db, membership)
    row = OffboardingService(db).get_offboarding_record(organization.id, record_id)
    return _record_read(row)
