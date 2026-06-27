import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.residency import (
    DataResidencyCheckRead,
    DataResidencyPolicyCreate,
    DataResidencyPolicyRead,
    DataResidencyPolicyUpdate,
    DataResidencySummaryRead,
    DataResidencySweepRead,
    DataResidencyViolationRead,
)
from app.data_observability.services.residency_service import ResidencyService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/residency", tags=["data-observability-residency"])


@router.post("/policies", response_model=DataResidencyPolicyRead, status_code=status.HTTP_201_CREATED)
def create_residency_policy(
    payload: DataResidencyPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyPolicyRead:
    row = ResidencyService(db).create_policy(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DataResidencyPolicyRead.model_validate(row)


@router.get("/policies", response_model=list[DataResidencyPolicyRead])
def list_residency_policies(
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataResidencyPolicyRead]:
    rows = ResidencyService(db).list_policies(organization.id, is_active=is_active)
    return [DataResidencyPolicyRead.model_validate(row) for row in rows]


@router.get("/policies/{policy_id}", response_model=DataResidencyPolicyRead)
def get_residency_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataResidencyPolicyRead:
    row = ResidencyService(db).get_policy(organization.id, policy_id)
    return DataResidencyPolicyRead.model_validate(row)


@router.patch("/policies/{policy_id}", response_model=DataResidencyPolicyRead)
def update_residency_policy(
    policy_id: uuid.UUID,
    payload: DataResidencyPolicyUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyPolicyRead:
    row = ResidencyService(db).update_policy(organization.id, policy_id, payload)
    db.commit()
    db.refresh(row)
    return DataResidencyPolicyRead.model_validate(row)


@router.post("/policies/{policy_id}/deactivate", response_model=DataResidencyPolicyRead)
def deactivate_residency_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyPolicyRead:
    row = ResidencyService(db).deactivate_policy(organization.id, policy_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataResidencyPolicyRead.model_validate(row)


@router.get("/violations", response_model=list[DataResidencyViolationRead])
def list_residency_violations(
    status_filter: str | None = Query(default=None, alias="status"),
    data_asset_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataResidencyViolationRead]:
    rows = ResidencyService(db).list_violations(organization.id, status_filter=status_filter, data_asset_id=data_asset_id)
    return [DataResidencyViolationRead.model_validate(row) for row in rows]


@router.post("/violations/{violation_id}/acknowledge", response_model=DataResidencyViolationRead)
def acknowledge_violation(
    violation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyViolationRead:
    row = ResidencyService(db).acknowledge_violation(organization.id, violation_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataResidencyViolationRead.model_validate(row)


@router.post("/violations/{violation_id}/resolve", response_model=DataResidencyViolationRead)
def resolve_violation(
    violation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyViolationRead:
    row = ResidencyService(db).resolve_violation(organization.id, violation_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataResidencyViolationRead.model_validate(row)


@router.post("/violations/{violation_id}/waive", response_model=DataResidencyViolationRead)
def waive_violation(
    violation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyViolationRead:
    row = ResidencyService(db).waive_violation(organization.id, violation_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataResidencyViolationRead.model_validate(row)


@router.get("/summary", response_model=DataResidencySummaryRead)
def get_residency_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataResidencySummaryRead:
    payload = ResidencyService(db).get_residency_summary(organization.id)
    return DataResidencySummaryRead.model_validate(payload)


@router.post("/check-asset/{asset_id}", response_model=DataResidencyCheckRead)
def check_single_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencyCheckRead:
    payload = ResidencyService(db).check_asset_residency(organization.id, asset_id)
    return DataResidencyCheckRead.model_validate(payload)


@router.post("/trigger-sweep", response_model=DataResidencySweepRead)
def trigger_residency_sweep(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataResidencySweepRead:
    payload = ResidencyService(db).run_residency_sweep(org_id=organization.id)
    db.commit()
    return DataResidencySweepRead.model_validate(payload)
