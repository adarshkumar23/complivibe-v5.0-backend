from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.pricing import (
    CompetitorPricingRefreshRequest,
    CompetitorPricingSnapshotRead,
)
from app.platform.services.competitor_pricing_service import CompetitorPricingService

router = APIRouter(prefix="/pricing", tags=["pricing"])


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
    _: Membership = Depends(require_permission("pricing:manage")),
) -> CompetitorPricingSnapshotRead:
    service = CompetitorPricingService(db)
    version = service.create_snapshot(
        entries=payload.entries,
        actor_user_id=current_user.id,
        actor_organization_id=organization.id,
        source_note=payload.source_note,
    )
    db.flush()
    result = service.latest_snapshot_payload()
    if str(result["version_id"]) != str(version.id):
        db.rollback()
        result = service.latest_snapshot_payload()
    db.commit()
    return CompetitorPricingSnapshotRead(**result)
