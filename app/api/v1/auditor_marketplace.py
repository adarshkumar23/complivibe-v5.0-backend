from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.auditor_engagement import AuditorEngagement
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auditor_marketplace import (
    AuditorEngagementCreate,
    AuditorEngagementCreateResponse,
    AuditorEngagementRead,
    AuditorRead,
)
from app.services.auditor_marketplace_service import AuditorMarketplaceService

public_router = APIRouter(tags=["auditor-marketplace"])
router = APIRouter(prefix="/auditor-marketplace", tags=["auditor-marketplace"])


def _auditor_read(row) -> AuditorRead:
    return AuditorRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        name=row.name,
        email=row.email,
        firm=row.firm,
        certifications_json=list(row.certifications_json or []),
        frameworks_json=list(row.frameworks_json or []),
        rate_usd_per_day=float(row.rate_usd_per_day),
        availability=row.availability,
        verified=bool(row.verified),
        bio=row.bio,
        status=row.status,
    )


def _engagement_read(row: AuditorEngagement) -> AuditorEngagementRead:
    return AuditorEngagementRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        auditor_id=row.auditor_id,
        audit_engagement_id=row.audit_engagement_id,
        framework=row.framework,
        status=row.status,
        started_at=row.started_at,
        revenue_share_fee_pct=float(row.revenue_share_fee_pct),
        notes=row.notes,
        created_by=row.created_by,
    )


@public_router.get("/find-auditor", response_model=list[AuditorRead])
def find_auditor(
    framework: str | None = Query(default=None),
    certification: str | None = Query(default=None),
    verified: bool | None = Query(default=None),
    max_rate_usd_per_day: float | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> list[AuditorRead]:
    rows = AuditorMarketplaceService(db).list_auditors(
        framework=framework,
        certification=certification,
        verified=verified,
        max_rate_usd_per_day=max_rate_usd_per_day,
    )
    db.commit()
    return [_auditor_read(row) for row in rows]


@router.post("/engagements", response_model=AuditorEngagementCreateResponse, status_code=status.HTTP_201_CREATED)
def create_auditor_engagement(
    payload: AuditorEngagementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("auditor_marketplace:engage")),
) -> AuditorEngagementCreateResponse:
    engagement, invitation_id, portal_token = AuditorMarketplaceService(db).create_engagement(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    db.commit()
    return AuditorEngagementCreateResponse(
        engagement=_engagement_read(engagement),
        portal_invitation_id=invitation_id,
        portal_token=portal_token,
    )


@router.get("/engagements", response_model=list[AuditorEngagementRead])
def list_auditor_engagements(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("auditor_marketplace:read")),
) -> list[AuditorEngagementRead]:
    rows = db.execute(
        select(AuditorEngagement)
        .where(AuditorEngagement.organization_id == organization.id)
        .order_by(AuditorEngagement.started_at.desc())
    ).scalars().all()
    return [_engagement_read(row) for row in rows]
