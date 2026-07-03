from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.platform.services.custom_role_service import CustomRoleService
from app.schemas.custom_role import AssignRoleRequest, CustomRoleCreateRequest, CustomRoleRead, CustomRoleUpdateRequest

router = APIRouter(prefix="/organizations", tags=["custom-roles"])


def _to_read_scoped(db: Session, org_id: uuid.UUID, role: Role) -> CustomRoleRead:
    return CustomRoleRead(
        id=role.id,
        organization_id=role.organization_id,
        name=role.name,
        description=role.description,
        is_system_role=bool(role.is_system_role),
        is_active=bool(role.is_active),
        permission_codes=CustomRoleService(db).get_role_permissions(org_id, role.id),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.post("/custom-roles", response_model=CustomRoleRead)
def create_custom_role(
    payload: CustomRoleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> CustomRoleRead:
    role = CustomRoleService(db).create_custom_role(
        organization.id,
        payload.name,
        payload.description,
        payload.permission_codes,
        current_user.id,
    )
    db.commit()
    db.refresh(role)
    return _to_read_scoped(db, organization.id, role)


@router.get("/custom-roles", response_model=list[CustomRoleRead])
def list_custom_roles(
    include_system: bool = True,
    include_custom: bool = True,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> list[CustomRoleRead]:
    rows = CustomRoleService(db).list_roles(organization.id, include_system=include_system, include_custom=include_custom)
    return [_to_read_scoped(db, organization.id, row) for row in rows]


@router.get("/custom-roles/{role_id}", response_model=CustomRoleRead)
def get_custom_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> CustomRoleRead:
    role = db.execute(select(Role).where(Role.id == role_id)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.organization_id not in {organization.id, None}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return _to_read_scoped(db, organization.id, role)


@router.patch("/custom-roles/{role_id}", response_model=CustomRoleRead)
def update_custom_role(
    role_id: uuid.UUID,
    payload: CustomRoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> CustomRoleRead:
    role = CustomRoleService(db).update_custom_role(
        organization.id,
        role_id,
        name=payload.name,
        description=payload.description,
        permission_codes=payload.permission_codes,
        updated_by=current_user.id,
    )
    db.commit()
    db.refresh(role)
    return _to_read_scoped(db, organization.id, role)


@router.post("/custom-roles/{role_id}/deactivate", response_model=CustomRoleRead)
def deactivate_custom_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> CustomRoleRead:
    role = CustomRoleService(db).deactivate_custom_role(organization.id, role_id, current_user.id)
    db.commit()
    db.refresh(role)
    return _to_read_scoped(db, organization.id, role)


@router.post("/memberships/{membership_id}/assign-role")
def assign_custom_role(
    membership_id: uuid.UUID,
    payload: AssignRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> dict:
    membership = CustomRoleService(db).assign_role_to_membership(
        organization.id,
        membership_id,
        payload.role_id,
        current_user.id,
    )
    db.commit()
    return {"membership_id": str(membership.id), "role_id": str(membership.role_id)}
