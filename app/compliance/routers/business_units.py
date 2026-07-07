from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.schemas.business_unit import (
    BusinessUnitCreate,
    BusinessUnitResponse,
    BusinessUnitUpdate,
    EntityTagRequest,
)
from app.compliance.services.business_unit_service import BusinessUnitService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User

router = APIRouter(prefix="/compliance/business-units", tags=["business-units"])


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _bu_response(service: BusinessUnitService, organization_id: uuid.UUID, row) -> BusinessUnitResponse:
    return BusinessUnitResponse.model_validate(service.business_unit_response_payload(organization_id, row))


@router.post("", response_model=BusinessUnitResponse, status_code=status.HTTP_201_CREATED)
def create_business_unit(
    payload: BusinessUnitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:write")),
) -> BusinessUnitResponse:
    _require_org_admin(db, membership)
    service = BusinessUnitService(db)
    row = service.create_bu(
        org_id=organization.id,
        name=payload.name,
        code=payload.code,
        parent_bu_id=payload.parent_bu_id,
        created_by=current_user.id,
        description=payload.description,
        cost_center=payload.cost_center,
        bu_lead_user_id=payload.bu_lead_user_id,
    )
    db.commit()
    db.refresh(row)
    return _bu_response(service, organization.id, row)


@router.get("", response_model=list[BusinessUnitResponse])
def list_business_units(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[BusinessUnitResponse]:
    service = BusinessUnitService(db)
    rows = service.list_bus(organization.id, include_inactive=include_inactive)
    return [_bu_response(service, organization.id, row) for row in rows]


@router.get("/tree", response_model=list[dict[str, Any]])
def get_business_unit_tree(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[dict[str, Any]]:
    return BusinessUnitService(db).get_bu_tree(organization.id)


@router.get("/{bu_id}", response_model=BusinessUnitResponse)
def get_business_unit(
    bu_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> BusinessUnitResponse:
    service = BusinessUnitService(db)
    row = service.get_bu(organization.id, bu_id)
    return _bu_response(service, organization.id, row)


@router.patch("/{bu_id}", response_model=BusinessUnitResponse)
def update_business_unit(
    bu_id: uuid.UUID,
    payload: BusinessUnitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:write")),
) -> BusinessUnitResponse:
    _require_org_admin(db, membership)
    service = BusinessUnitService(db)
    row = service.update_bu(organization.id, bu_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _bu_response(service, organization.id, row)


@router.post("/{bu_id}/deactivate", response_model=BusinessUnitResponse)
def deactivate_business_unit(
    bu_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:write")),
) -> BusinessUnitResponse:
    _require_org_admin(db, membership)
    service = BusinessUnitService(db)
    row = service.deactivate_bu(organization.id, bu_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _bu_response(service, organization.id, row)


@router.delete("/{bu_id}", response_model=BusinessUnitResponse)
def delete_business_unit(
    bu_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:write")),
) -> BusinessUnitResponse:
    _require_org_admin(db, membership)
    service = BusinessUnitService(db)
    row = service.delete_bu(organization.id, bu_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _bu_response(service, organization.id, row)


@router.get("/{bu_id}/summary", response_model=dict[str, Any])
def get_business_unit_summary(
    bu_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict[str, Any]:
    return BusinessUnitService(db).get_bu_summary(organization.id, bu_id)


@router.post("/tag", response_model=dict[str, str | None])
def tag_entity_to_business_unit(
    payload: EntityTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> dict[str, str | None]:
    result = BusinessUnitService(db).tag_entity(
        org_id=organization.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        business_unit_id=payload.business_unit_id,
        user_id=current_user.id,
    )
    db.commit()
    return result
