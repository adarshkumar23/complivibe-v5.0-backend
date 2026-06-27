import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.retention import (
    ApplyPolicyRequest,
    DataRetentionPolicyCreate,
    DataRetentionPolicyRead,
    DataRetentionPolicyUpdate,
    DataRetentionReviewRead,
    ResolveReviewRequest,
    RetentionSummaryRead,
    RetentionSweepRead,
    WaiveReviewRequest,
)
from app.data_observability.services.retention_service import RetentionService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/retention", tags=["data-observability-retention"])


@router.post("/policies", response_model=DataRetentionPolicyRead, status_code=status.HTTP_201_CREATED)
def create_retention_policy(
    payload: DataRetentionPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataRetentionPolicyRead:
    row = RetentionService(db).create_policy(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DataRetentionPolicyRead.model_validate(row)


@router.get("/policies", response_model=list[DataRetentionPolicyRead])
def list_retention_policies(
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataRetentionPolicyRead]:
    rows = RetentionService(db).list_policies(organization.id, is_active=is_active)
    return [DataRetentionPolicyRead.model_validate(row) for row in rows]


@router.get("/policies/{policy_id}", response_model=DataRetentionPolicyRead)
def get_retention_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataRetentionPolicyRead:
    row = RetentionService(db).get_policy(organization.id, policy_id)
    return DataRetentionPolicyRead.model_validate(row)


@router.patch("/policies/{policy_id}", response_model=DataRetentionPolicyRead)
def update_retention_policy(
    policy_id: uuid.UUID,
    payload: DataRetentionPolicyUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataRetentionPolicyRead:
    row = RetentionService(db).update_policy(organization.id, policy_id, payload)
    db.commit()
    db.refresh(row)
    return DataRetentionPolicyRead.model_validate(row)


@router.post("/policies/{policy_id}/deactivate", response_model=DataRetentionPolicyRead)
def deactivate_retention_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataRetentionPolicyRead:
    row = RetentionService(db).deactivate_policy(organization.id, policy_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataRetentionPolicyRead.model_validate(row)


@router.post("/policies/{policy_id}/apply-to-asset", response_model=dict)
def apply_policy_to_asset(
    policy_id: uuid.UUID,
    payload: ApplyPolicyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> dict:
    row = RetentionService(db).apply_policy_to_asset(organization.id, payload.data_asset_id, policy_id, current_user.id)
    db.commit()
    return {
        "data_asset_id": str(row.id),
        "retention_policy_days": row.retention_policy_days,
        "retention_review_date": row.retention_review_date.isoformat() if row.retention_review_date else None,
    }


@router.get("/reviews", response_model=list[DataRetentionReviewRead])
def list_retention_reviews(
    status_filter: str | None = Query(default=None, alias="status"),
    data_asset_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataRetentionReviewRead]:
    rows = RetentionService(db).list_reviews(organization.id, status_filter=status_filter, data_asset_id=data_asset_id)
    return [DataRetentionReviewRead.model_validate(row) for row in rows]


@router.post("/reviews/{review_id}/resolve", response_model=DataRetentionReviewRead)
def resolve_retention_review(
    review_id: uuid.UUID,
    payload: ResolveReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataRetentionReviewRead:
    row = RetentionService(db).resolve_review(organization.id, review_id, current_user.id, payload.evidence_notes)
    db.commit()
    db.refresh(row)
    return DataRetentionReviewRead.model_validate(row)


@router.post("/reviews/{review_id}/waive", response_model=DataRetentionReviewRead)
def waive_retention_review(
    review_id: uuid.UUID,
    payload: WaiveReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataRetentionReviewRead:
    row = RetentionService(db).waive_review(organization.id, review_id, current_user.id, payload.reason)
    db.commit()
    db.refresh(row)
    return DataRetentionReviewRead.model_validate(row)


@router.get("/summary", response_model=RetentionSummaryRead)
def get_retention_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> RetentionSummaryRead:
    payload = RetentionService(db).get_retention_summary(organization.id)
    return RetentionSummaryRead.model_validate(payload)


@router.post("/trigger-sweep", response_model=RetentionSweepRead)
def trigger_retention_sweep(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> RetentionSweepRead:
    payload = RetentionService(db).run_retention_sweep(org_id=organization.id)
    db.commit()
    return RetentionSweepRead.model_validate(payload)
