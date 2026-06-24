from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.repositories.role_repository import RoleRepository
from app.schemas.role import RoleRead
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleRead])
def list_roles(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:read")),
) -> list[RoleRead]:
    roles = RoleRepository(db).list_by_organization(organization.id)
    return [
        RoleRead(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            permissions=RBACService.get_role_permissions(db, role.id),
        )
        for role in roles
    ]
