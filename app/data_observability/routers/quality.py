import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.quality import (
    DataQualityConfigCreate,
    DataQualityConfigRead,
    DataQualityConfigUpdate,
    DataQualityDashboardRead,
    DataQualityReadingCreate,
    DataQualityReadingRead,
)
from app.data_observability.services.quality_service import DataQualityService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/quality", tags=["data-observability-quality"])


@router.post("/configs", response_model=DataQualityConfigRead, status_code=status.HTTP_201_CREATED)
def create_quality_config(
    payload: DataQualityConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataQualityConfigRead:
    row = DataQualityService(db).create_config(organization.id, payload.data_asset_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DataQualityConfigRead.model_validate(row)


@router.get("/configs", response_model=list[DataQualityConfigRead])
def list_quality_configs(
    data_asset_id: uuid.UUID | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataQualityConfigRead]:
    rows = DataQualityService(db).list_configs(
        organization.id,
        data_asset_id=data_asset_id,
        metric_type=metric_type,
        is_active=is_active,
    )
    return [DataQualityConfigRead.model_validate(row) for row in rows]


@router.get("/configs/{config_id}", response_model=DataQualityConfigRead)
def get_quality_config(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataQualityConfigRead:
    row = DataQualityService(db).get_config(organization.id, config_id)
    return DataQualityConfigRead.model_validate(row)


@router.patch("/configs/{config_id}", response_model=DataQualityConfigRead)
def update_quality_config(
    config_id: uuid.UUID,
    payload: DataQualityConfigUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataQualityConfigRead:
    row = DataQualityService(db).update_config(organization.id, config_id, payload)
    db.commit()
    db.refresh(row)
    return DataQualityConfigRead.model_validate(row)


@router.post("/configs/{config_id}/deactivate", response_model=DataQualityConfigRead)
def deactivate_quality_config(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataQualityConfigRead:
    row = DataQualityService(db).deactivate_config(organization.id, config_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataQualityConfigRead.model_validate(row)


@router.post("/configs/{config_id}/readings", response_model=DataQualityReadingRead, status_code=status.HTTP_201_CREATED)
def submit_quality_reading(
    config_id: uuid.UUID,
    payload: DataQualityReadingCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataQualityReadingRead:
    row = DataQualityService(db).submit_reading(
        organization.id,
        config_id,
        payload.value,
        reading_source="manual",
        source_tool=payload.source_tool,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return DataQualityReadingRead.model_validate(row)


@router.get("/dashboard", response_model=DataQualityDashboardRead)
def get_quality_dashboard(
    data_asset_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataQualityDashboardRead:
    payload = DataQualityService(db).get_quality_dashboard(organization.id, data_asset_id=data_asset_id)
    return DataQualityDashboardRead.model_validate(payload)
