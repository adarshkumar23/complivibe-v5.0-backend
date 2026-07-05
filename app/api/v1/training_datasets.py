import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.training_dataset import (
    TrainingDataRightsGaps,
    TrainingDatasetCreate,
    TrainingDatasetResponse,
    TrainingDatasetUpdate,
)
from app.services.training_dataset_service import TrainingDatasetService

router = APIRouter(prefix="/training-datasets", tags=["training-datasets"])

PERMISSION = "training_data_rights:manage"


@router.post("", response_model=TrainingDatasetResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=TrainingDatasetResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_training_dataset(
    payload: TrainingDatasetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(PERMISSION)),
) -> TrainingDatasetResponse:
    service = TrainingDatasetService(db)
    row = service.create(organization.id, payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return TrainingDatasetResponse.model_validate(row)


@router.get("", response_model=list[TrainingDatasetResponse])
@router.get("/", response_model=list[TrainingDatasetResponse], include_in_schema=False)
def list_training_datasets(
    license_type: str | None = Query(default=None),
    linked_ai_system_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(PERMISSION)),
) -> list[TrainingDatasetResponse]:
    rows = TrainingDatasetService(db).list(
        organization.id,
        license_type=license_type,
        linked_ai_system_id=linked_ai_system_id,
    )
    return [TrainingDatasetResponse.model_validate(row) for row in rows]


@router.get("/rights-gaps", response_model=TrainingDataRightsGaps)
def get_rights_gaps(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(PERMISSION)),
) -> TrainingDataRightsGaps:
    payload = TrainingDatasetService(db).rights_gaps(organization.id)
    return TrainingDataRightsGaps.model_validate(payload)


@router.get("/{dataset_id}", response_model=TrainingDatasetResponse)
def get_training_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(PERMISSION)),
) -> TrainingDatasetResponse:
    row = TrainingDatasetService(db).get(organization.id, dataset_id)
    return TrainingDatasetResponse.model_validate(row)


@router.patch("/{dataset_id}", response_model=TrainingDatasetResponse)
def update_training_dataset(
    dataset_id: uuid.UUID,
    payload: TrainingDatasetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(PERMISSION)),
) -> TrainingDatasetResponse:
    service = TrainingDatasetService(db)
    row = service.update(organization.id, dataset_id, payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return TrainingDatasetResponse.model_validate(row)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(PERMISSION)),
) -> None:
    service = TrainingDatasetService(db)
    service.delete(organization.id, dataset_id, actor_user_id=current_user.id)
    db.commit()
    return None
