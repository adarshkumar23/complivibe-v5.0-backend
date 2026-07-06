from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.pricing import (
    CompetitorPricingRefreshRequest,
    CompetitorPricingSnapshotRead,
)
from app.platform.services.competitor_pricing_service import CompetitorPricingService

router = APIRouter(prefix="/pricing", tags=["pricing"])


def _require_platform_admin(current_user: User) -> None:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator privileges required for this operation",
        )


@router.get("", response_model=CompetitorPricingSnapshotRead)
def get_pricing_snapshot(db: Session = Depends(get_db)) -> CompetitorPricingSnapshotRead:
    payload = CompetitorPricingService(db).latest_snapshot_payload()
    db.commit()
    return CompetitorPricingSnapshotRead(**payload)


@router.post("/refresh", response_model=CompetitorPricingSnapshotRead, status_code=status.HTTP_201_CREATED)
def refresh_pricing_snapshot(
    payload: CompetitorPricingRefreshRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> CompetitorPricingSnapshotRead:
    _require_platform_admin(current_user)
    service = CompetitorPricingService(db)
    version = service.create_snapshot(
        entries=payload.entries,
        actor_user_id=current_user.id,
        actor_organization_id=organization.id,
        actor_is_superuser=current_user.is_superuser,
        source_note=payload.source_note,
    )
    db.flush()
    result = service.latest_snapshot_payload()
    if str(result["version_id"]) != str(version.id):
        db.rollback()
        result = service.latest_snapshot_payload()
    db.commit()
    return CompetitorPricingSnapshotRead(**result)
