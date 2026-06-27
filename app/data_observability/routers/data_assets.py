import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.data_assets import (
    DataAssetClassifySampleRequest,
    DataAssetConfirmClassificationRequest,
    DataAssetCreate,
    DataAssetRead,
    DataAssetSampleClassificationRead,
    DataAssetSummaryRead,
    DataAssetUpdate,
)
from app.data_observability.schemas.access_monitoring import DataAccessLogRead
from app.data_observability.schemas.data_obligations import (
    DataAssetObligationLinkCreate,
    DataAssetObligationLinkRead,
    DataObligationSuggestionRead,
)
from app.data_observability.schemas.quality import DataQualityConfigRead
from app.data_observability.schemas.residency import DataResidencyCheckRead
from app.data_observability.services.access_monitoring_service import AccessMonitoringService
from app.data_observability.services.data_obligation_service import DataObligationService
from app.data_observability.services.data_asset_service import DataAssetService
from app.data_observability.services.quality_service import DataQualityService
from app.data_observability.services.residency_service import ResidencyService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/assets", tags=["data-observability-assets"])


@router.post("", response_model=DataAssetRead, status_code=status.HTTP_201_CREATED)
def create_data_asset(
    payload: DataAssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAssetRead:
    row = DataAssetService(db).create_asset(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DataAssetRead.model_validate(row)


@router.get("", response_model=list[DataAssetRead])
def list_data_assets(
    asset_type: str | None = Query(default=None),
    sensitivity_tier: str | None = Query(default=None),
    classification_type: str | None = Query(default=None),
    classification_confirmed: bool | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataAssetRead]:
    rows = DataAssetService(db).list_assets(
        organization.id,
        asset_type=asset_type,
        sensitivity_tier=sensitivity_tier,
        classification_type=classification_type,
        classification_confirmed=classification_confirmed,
        status_filter=status_filter,
        skip=skip,
        limit=limit,
    )
    return [DataAssetRead.model_validate(row) for row in rows]


@router.get("/summary", response_model=DataAssetSummaryRead)
def get_data_asset_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataAssetSummaryRead:
    payload = DataAssetService(db).get_summary(organization.id)
    return DataAssetSummaryRead.model_validate(payload)


@router.get("/{asset_id}", response_model=DataAssetRead)
def get_data_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataAssetRead:
    row = DataAssetService(db).get_asset(organization.id, asset_id)
    return DataAssetRead.model_validate(row)


@router.patch("/{asset_id}", response_model=DataAssetRead)
def update_data_asset(
    asset_id: uuid.UUID,
    payload: DataAssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAssetRead:
    row = DataAssetService(db).update_asset(organization.id, asset_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DataAssetRead.model_validate(row)


@router.post("/{asset_id}/confirm-classification", response_model=DataAssetRead)
def confirm_data_asset_classification(
    asset_id: uuid.UUID,
    payload: DataAssetConfirmClassificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAssetRead:
    row = DataAssetService(db).confirm_classification(
        organization.id,
        asset_id,
        payload.classification_type,
        payload.sensitivity_tier,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return DataAssetRead.model_validate(row)


@router.post("/{asset_id}/classify-sample", response_model=DataAssetSampleClassificationRead)
def classify_data_asset_sample(
    asset_id: uuid.UUID,
    payload: DataAssetClassifySampleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAssetSampleClassificationRead:
    result = DataAssetService(db).classify_sample(
        organization.id,
        asset_id,
        sample_text=payload.sample_text,
        user_id=current_user.id,
        language=payload.language,
    )
    db.commit()
    return DataAssetSampleClassificationRead.model_validate(result)


@router.delete("/{asset_id}", response_model=DataAssetRead)
def delete_data_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAssetRead:
    row = DataAssetService(db).soft_delete_asset(organization.id, asset_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataAssetRead.model_validate(row)


@router.get("/{asset_id}/quality-configs", response_model=list[DataQualityConfigRead])
def list_asset_quality_configs(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataQualityConfigRead]:
    rows = DataQualityService(db).list_configs(organization.id, data_asset_id=asset_id)
    return [DataQualityConfigRead.model_validate(row) for row in rows]


@router.get("/{asset_id}/access-logs", response_model=list[DataAccessLogRead])
def list_asset_access_logs(
    asset_id: uuid.UUID,
    from_time: datetime | None = Query(default=None),
    to_time: datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataAccessLogRead]:
    rows = AccessMonitoringService(db).list_access_logs(
        organization.id,
        data_asset_id=asset_id,
        from_time=from_time,
        to_time=to_time,
        skip=skip,
        limit=limit,
    )
    return [DataAccessLogRead.model_validate(row) for row in rows]


@router.post("/{asset_id}/obligation-links", response_model=DataAssetObligationLinkRead, status_code=status.HTTP_201_CREATED)
def link_asset_to_obligation(
    asset_id: uuid.UUID,
    payload: DataAssetObligationLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAssetObligationLinkRead:
    service = DataObligationService(db)
    row = service.link_asset_to_obligation(
        organization.id,
        asset_id,
        payload.obligation_id,
        payload.link_type,
        current_user.id,
        justification=payload.justification,
    )
    db.commit()
    links = service.get_asset_obligations(organization.id, asset_id)
    match = next(item for item in links if item["obligation_id"] == str(payload.obligation_id))
    return DataAssetObligationLinkRead.model_validate(match)


@router.delete("/{asset_id}/obligation-links/{obligation_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_asset_from_obligation(
    asset_id: uuid.UUID,
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> None:
    DataObligationService(db).unlink_asset_from_obligation(organization.id, asset_id, obligation_id, current_user.id)
    db.commit()
    return None


@router.get("/{asset_id}/obligation-links", response_model=list[DataAssetObligationLinkRead])
def list_asset_obligation_links(
    asset_id: uuid.UUID,
    link_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataAssetObligationLinkRead]:
    rows = DataObligationService(db).get_asset_obligations(organization.id, asset_id, link_type=link_type)
    return [DataAssetObligationLinkRead.model_validate(row) for row in rows]


@router.get("/{asset_id}/suggest-obligations", response_model=list[DataObligationSuggestionRead])
def suggest_asset_obligations(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataObligationSuggestionRead]:
    rows = DataObligationService(db).suggest_obligations(organization.id, asset_id)
    return [DataObligationSuggestionRead.model_validate(row) for row in rows]


@router.get("/{asset_id}/residency-status", response_model=DataResidencyCheckRead)
def get_asset_residency_status(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataResidencyCheckRead:
    payload = ResidencyService(db).check_asset_residency(organization.id, asset_id)
    return DataResidencyCheckRead.model_validate(payload)
