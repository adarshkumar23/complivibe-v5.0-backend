from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.services.scim_service import SCIMService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:read")),
) -> list[UserRead]:
    """List users belonging to the current organization.

    Reuses the same org-scoped user query that backs the SCIM
    `GET /scim/v2/Users` endpoint (`SCIMService.org_users_query`), shaped
    to this endpoint's own `UserRead` response contract rather than the
    SCIM wire format.
    """
    query = SCIMService.org_users_query(organization.id).offset(skip).limit(limit)
    rows = db.execute(query).scalars().all()
    return [UserRead.model_validate(row) for row in rows]
