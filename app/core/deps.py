import uuid
from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db as get_db_session
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.services.rbac_service import RBACService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def get_current_user(db: Annotated[Session, Depends(get_db)], token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not subject:
            raise ValueError("Missing token subject")
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials") from exc

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return user


def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_active or current_user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user


def get_current_organization(
    db: Annotated[Session, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> Organization:
    if not x_organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Organization-ID header")

    try:
        organization_id = uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Organization-ID header") from exc

    organization = db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def require_org_membership(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    organization: Annotated[Organization, Depends(get_current_organization)],
) -> Membership:
    membership = RBACService.get_user_membership(db, current_user.id, organization.id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this organization")
    return membership


def require_permission(permission_code: str) -> Callable[..., Membership]:
    def dependency(
        db: Annotated[Session, Depends(get_db)],
        current_user: Annotated[User, Depends(get_current_active_user)],
        membership: Annotated[Membership, Depends(require_org_membership)],
    ) -> Membership:
        has_permission = RBACService.user_has_permission(db, current_user.id, membership.organization_id, permission_code)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_code}",
            )
        return membership

    return dependency
