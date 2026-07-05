from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.ip_asset import IPAsset
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.ip_asset import (
    IP_ASSET_STATUSES,
    IP_ASSET_TYPES,
    ExpiringIPAssetResponse,
    IPAssetCreate,
    IPAssetResponse,
    IPAssetSettingsResponse,
    IPAssetSettingsUpdate,
    IPAssetUpdate,
)
from app.services.ip_asset_service import IPAssetService

router = APIRouter(prefix="/ip-assets", tags=["ip-assets"])


def _to_response(service: IPAssetService, row: IPAsset) -> IPAssetResponse:
    is_expiring_soon, is_expired, days_until_expiry = service.compute_expiry_fields(row)
    return IPAssetResponse(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        asset_type=row.asset_type,
        licensor=row.licensor,
        licensee=row.licensee,
        terms=row.terms,
        expiry_date=row.expiry_date,
        linked_ai_system_id=row.linked_ai_system_id,
        status=row.status,
        created_by=row.created_by,
        is_expiring_soon=is_expiring_soon,
        is_expired=is_expired,
        days_until_expiry=days_until_expiry,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _settings_response(row) -> IPAssetSettingsResponse:
    return IPAssetSettingsResponse(
        id=row.id,
        organization_id=row.organization_id,
        expiring_soon_window_days=row.expiring_soon_window_days,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=IPAssetResponse, status_code=status.HTTP_201_CREATED)
def create_ip_asset(
    payload: IPAssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:manage")),
) -> IPAssetResponse:
    service = IPAssetService(db)
    row = service.create_asset(organization.id, payload.model_dump(), current_user.id)
    db.commit()
    db.refresh(row)
    return _to_response(service, row)


@router.get("", response_model=list[IPAssetResponse])
def list_ip_assets(
    asset_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:read")),
) -> list[IPAssetResponse]:
    service = IPAssetService(db)
    rows = service.list_assets(organization.id, asset_type=asset_type, status_filter=status_filter)
    return [_to_response(service, row) for row in rows]


@router.get("/expiring-soon", response_model=list[ExpiringIPAssetResponse])
def get_expiring_soon_ip_assets(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:read")),
) -> list[ExpiringIPAssetResponse]:
    service = IPAssetService(db)
    ranked = service.expiring_soon(organization.id)
    responses = []
    for item in ranked:
        base = _to_response(service, item["asset"])
        responses.append(
            ExpiringIPAssetResponse(
                **base.model_dump(),
                at_risk_ai_system=item["at_risk_ai_system"],
            )
        )
    return responses


@router.get("/settings", response_model=IPAssetSettingsResponse)
def get_ip_asset_settings(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:read")),
) -> IPAssetSettingsResponse:
    service = IPAssetService(db)
    row = service.get_or_create_settings(organization.id)
    db.commit()
    db.refresh(row)
    return _settings_response(row)


@router.patch("/settings", response_model=IPAssetSettingsResponse)
def update_ip_asset_settings(
    payload: IPAssetSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:manage")),
) -> IPAssetSettingsResponse:
    service = IPAssetService(db)
    row = service.update_settings(organization.id, payload.expiring_soon_window_days, current_user.id)
    db.commit()
    db.refresh(row)
    return _settings_response(row)


@router.get("/{asset_id}", response_model=IPAssetResponse)
def get_ip_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:read")),
) -> IPAssetResponse:
    service = IPAssetService(db)
    row = service.get_asset(organization.id, asset_id)
    return _to_response(service, row)


@router.patch("/{asset_id}", response_model=IPAssetResponse)
def update_ip_asset(
    asset_id: UUID,
    payload: IPAssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:manage")),
) -> IPAssetResponse:
    service = IPAssetService(db)
    update_fields = payload.model_dump(exclude_unset=True)
    row = service.update_asset(organization.id, asset_id, update_fields, current_user.id)
    db.commit()
    db.refresh(row)
    return _to_response(service, row)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ip_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ip_assets:manage")),
) -> None:
    service = IPAssetService(db)
    service.delete_asset(organization.id, asset_id, current_user.id)
    db.commit()


__all__ = ["router", "IP_ASSET_TYPES", "IP_ASSET_STATUSES"]
