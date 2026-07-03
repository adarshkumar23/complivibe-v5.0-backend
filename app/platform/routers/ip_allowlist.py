from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.platform.services.ip_allowlist_service import IPAllowlistService
from app.schemas.session_management import IPAllowlistCreateRequest, IPAllowlistRead

router = APIRouter(prefix="/organizations/ip-allowlist", tags=["ip-allowlist"])


@router.post("", response_model=IPAllowlistRead)
def add_ip_allowlist_range(
    payload: IPAllowlistCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> IPAllowlistRead:
    requester_ip = IPAllowlistService.extract_request_ip(
        x_forwarded_for=request.headers.get("X-Forwarded-For"),
        client_host=request.client.host if request.client else None,
    )
    row = IPAllowlistService(db).add_ip_range(
        org_id=organization.id,
        cidr_range=payload.cidr_range,
        label=payload.label,
        created_by=current_user.id,
        requester_ip=requester_ip,
    )
    db.commit()
    db.refresh(row)
    return IPAllowlistRead.model_validate(row)


@router.get("", response_model=list[IPAllowlistRead])
def list_ip_allowlist_ranges(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> list[IPAllowlistRead]:
    rows = IPAllowlistService(db).list_ranges(org_id=organization.id)
    return [IPAllowlistRead.model_validate(row) for row in rows]


@router.delete("/{range_id}", response_model=IPAllowlistRead)
def deactivate_ip_allowlist_range(
    range_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> IPAllowlistRead:
    row = IPAllowlistService(db).remove_ip_range(org_id=organization.id, range_id=range_id)
    db.commit()
    db.refresh(row)
    return IPAllowlistRead.model_validate(row)
