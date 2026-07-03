import uuid
from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db as get_db_session
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.platform.services.ip_allowlist_service import IPAllowlistService
from app.platform.services.session_service import SessionService
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
        token_id = payload.get("jti")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials") from exc

    if isinstance(token_id, str) and token_id:
        if not SessionService(db).validate_and_touch_session(token_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

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
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    organization: Annotated[Organization, Depends(get_current_organization)],
) -> Membership:
    membership = RBACService.get_user_membership(db, current_user.id, organization.id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this organization")

    request_ip = IPAllowlistService.extract_request_ip(
        x_forwarded_for=request.headers.get("X-Forwarded-For"),
        client_host=request.client.host if request.client else None,
    )
    if not IPAllowlistService(db).is_ip_allowed(org_id=organization.id, request_ip=request_ip):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request IP is not allowed for this organization")
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
