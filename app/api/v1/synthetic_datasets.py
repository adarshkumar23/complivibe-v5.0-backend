import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.synthetic_dataset import SyntheticDataset
from app.models.user import User
from app.schemas.synthetic_dataset import (
    SyntheticDatasetCreate,
    SyntheticDatasetRead,
    SyntheticDatasetUpdate,
    SyntheticDatasetValidateRequest,
)
from app.services.synthetic_dataset_service import SyntheticDatasetService

router = APIRouter(prefix="/synthetic-datasets", tags=["synthetic-datasets"])


def _read(service: SyntheticDatasetService, row: SyntheticDataset) -> SyntheticDatasetRead:
    return SyntheticDatasetRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        generation_method=row.generation_method,
        source_dataset_id=row.source_dataset_id,
        privacy_technique=row.privacy_technique,
        privacy_parameter=row.privacy_parameter,
        reidentification_risk_score=row.reidentification_risk_score,
        validation_status=row.validation_status,
        validation_notes=row.validation_notes,
        governance_gap_flag=row.governance_gap_flag,
        governance_gap_reason=service.gap_reason(row),
        created_by=row.created_by,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=SyntheticDatasetRead, status_code=status.HTTP_201_CREATED)
def create_synthetic_dataset(
    payload: SyntheticDatasetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> SyntheticDatasetRead:
    service = SyntheticDatasetService(db)
    row = service.create_dataset(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        data=payload.model_dump(),
    )
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.get("", response_model=list[SyntheticDatasetRead])
def list_synthetic_datasets(
    validation_status: str | None = Query(default=None),
    privacy_technique: str | None = Query(default=None),
    governance_gap_flag: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> list[SyntheticDatasetRead]:
    service = SyntheticDatasetService(db)
    rows = service.list_datasets(
        organization.id,
        validation_status=validation_status,
        privacy_technique=privacy_technique,
        governance_gap_flag=governance_gap_flag,
    )
    return [_read(service, row) for row in rows]


@router.get("/governance-gaps", response_model=list[SyntheticDatasetRead])
def list_governance_gaps(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> list[SyntheticDatasetRead]:
    service = SyntheticDatasetService(db)
    rows = service.list_governance_gaps(organization.id)
    return [_read(service, row) for row in rows]


@router.get("/{dataset_id}", response_model=SyntheticDatasetRead)
def get_synthetic_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> SyntheticDatasetRead:
    service = SyntheticDatasetService(db)
    row = service.require_dataset_in_org(organization.id, dataset_id)
    return _read(service, row)


@router.patch("/{dataset_id}", response_model=SyntheticDatasetRead)
def update_synthetic_dataset(
    dataset_id: uuid.UUID,
    payload: SyntheticDatasetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> SyntheticDatasetRead:
    service = SyntheticDatasetService(db)
    row = service.update_dataset(
        organization_id=organization.id,
        dataset_id=dataset_id,
        actor_user_id=current_user.id,
        changes=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.post("/{dataset_id}/validate", response_model=SyntheticDatasetRead)
def validate_synthetic_dataset(
    dataset_id: uuid.UUID,
    payload: SyntheticDatasetValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> SyntheticDatasetRead:
    service = SyntheticDatasetService(db)
    row = service.set_validation_status(
        organization_id=organization.id,
        dataset_id=dataset_id,
        actor_user_id=current_user.id,
        new_status=payload.validation_status,
        notes=payload.validation_notes,
    )
    db.commit()
    db.refresh(row)
    return _read(service, row)


@router.delete("/{dataset_id}", response_model=SyntheticDatasetRead)
def delete_synthetic_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("synthetic_data:manage")),
) -> SyntheticDatasetRead:
    service = SyntheticDatasetService(db)
    row = service.soft_delete_dataset(
        organization_id=organization.id,
        dataset_id=dataset_id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _read(service, row)
