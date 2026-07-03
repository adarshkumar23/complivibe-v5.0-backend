from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.models.organization import Organization
from app.models.rate_limit_config import RateLimitConfig
from app.models.user import User
from app.platform.services.rate_limit_service import RateLimitService

router = APIRouter(tags=["rate-limits"])


class RateLimitConfigResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    endpoint_group: str
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int | None
    burst_allowance: int
    is_active: bool


class OrgRateLimitUpsertRequest(BaseModel):
    endpoint_group: Literal["api_general", "ingest", "auth", "reports", "public", "ai_governance", "scim"]
    rpm: int = Field(ge=1, le=10000)
    rph: int = Field(ge=1, le=500000)


def _require_superuser(current_user: User) -> None:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser privileges required")


def _as_response(rows: list[RateLimitConfig]) -> list[RateLimitConfigResponse]:
    return [
        RateLimitConfigResponse(
            id=row.id,
            organization_id=row.organization_id,
            endpoint_group=row.endpoint_group,
            requests_per_minute=row.requests_per_minute,
            requests_per_hour=row.requests_per_hour,
            requests_per_day=row.requests_per_day,
            burst_allowance=row.burst_allowance,
            is_active=row.is_active,
        )
        for row in rows
    ]


@router.get("/admin/rate-limits/defaults", response_model=list[RateLimitConfigResponse])
def get_platform_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[RateLimitConfigResponse]:
    _require_superuser(current_user)
    rows = RateLimitService().get_platform_defaults(db)
    return _as_response(rows)


@router.get("/admin/rate-limits/org/{org_id}", response_model=list[RateLimitConfigResponse])
def get_org_overrides(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[RateLimitConfigResponse]:
    _require_superuser(current_user)
    rows = RateLimitService().get_org_config(org_id, db)
    return _as_response(rows)


@router.put("/admin/rate-limits/org/{org_id}", response_model=RateLimitConfigResponse)
def set_org_override(
    org_id: uuid.UUID,
    payload: OrgRateLimitUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RateLimitConfigResponse:
    _require_superuser(current_user)
    row = RateLimitService().set_org_limit(
        org_id=org_id,
        endpoint_group=payload.endpoint_group,
        requests_per_minute=payload.rpm,
        requests_per_hour=payload.rph,
        created_by=current_user.id,
        db=db,
    )
    db.commit()
    db.refresh(row)
    return RateLimitConfigResponse(
        id=row.id,
        organization_id=row.organization_id,
        endpoint_group=row.endpoint_group,
        requests_per_minute=row.requests_per_minute,
        requests_per_hour=row.requests_per_hour,
        requests_per_day=row.requests_per_day,
        burst_allowance=row.burst_allowance,
        is_active=row.is_active,
    )


@router.delete("/admin/rate-limits/org/{org_id}/{group}", status_code=status.HTTP_204_NO_CONTENT)
def reset_org_override(
    org_id: uuid.UUID,
    group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    _require_superuser(current_user)
    RateLimitService().reset_to_default(org_id=org_id, endpoint_group=group, user_id=current_user.id, db=db)
    db.commit()


@router.get("/rate-limits/my-limits")
def get_my_limits(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> dict:
    service = RateLimitService()
    platform_defaults = {item.endpoint_group: item for item in service.get_platform_defaults(db)}
    org_overrides = {item.endpoint_group: item for item in service.get_org_config(organization.id, db)}

    endpoint_groups = sorted(set(platform_defaults.keys()) | set(org_overrides.keys()))
    limits: list[dict] = []
    for group in endpoint_groups:
        source = "org_override" if group in org_overrides else "platform_default"
        row = org_overrides.get(group) or platform_defaults[group]
        limits.append(
            {
                "endpoint_group": group,
                "source": source,
                "requests_per_minute": row.requests_per_minute,
                "requests_per_hour": row.requests_per_hour,
                "requests_per_day": row.requests_per_day,
                "burst_allowance": row.burst_allowance,
            }
        )

    return {
        "organization_id": str(organization.id),
        "limits": limits,
        "usage_hint": "Rate limits are enforced per key scope (org/user, api key, or IP).",
    }


@router.get("/admin/sentry-test")
def sentry_test_endpoint(
    current_user: User = Depends(get_current_active_user),
) -> None:
    _require_superuser(current_user)
    raise Exception("Sentry test — this is intentional, confirms error monitoring is wired")
