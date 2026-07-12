import secrets
import uuid
from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
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

SESSION_COOKIE_NAME = "cv_session"
CSRF_COOKIE_NAME = "cv_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BearerOrSessionCookie(OAuth2PasswordBearer):
    """Same as OAuth2PasswordBearer, but also accepts the httpOnly session cookie.

    Kept as an OAuth2PasswordBearer subclass (rather than a bare function) so it still
    shows up correctly as a security scheme in the generated OpenAPI docs, and so the
    dependency keeps the exact same "raise 401 immediately if nothing is provided"
    behavior plain `Depends(oauth2_scheme)` always had -- the cookie is just a second
    acceptable credential source alongside the Authorization header.
    """

    async def __call__(self, request: Request) -> str | None:
        authorization = request.headers.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)
        if authorization and scheme.lower() == "bearer":
            return param
        cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
        if cookie_token:
            return cookie_token
        if self.auto_error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return None


oauth2_scheme = BearerOrSessionCookie(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    # Bearer header takes priority in the scheme's own __call__ above; whatever's left
    # here that isn't from an Authorization header must have come from the cookie.
    from_cookie = not request.headers.get("Authorization")
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not subject:
            raise ValueError("Missing token subject")
        user_id = uuid.UUID(subject)
        token_id = payload.get("jti")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials") from exc

    # Bearer-header auth isn't automatically attached by browsers, so it carries no
    # CSRF risk. Cookie auth is ambient, so mutating requests must also present a
    # matching CSRF token (double-submit, bound to this specific session via the
    # signed "csrf" claim) proving the caller can read non-httpOnly response data,
    # i.e. isn't a blind cross-site form/fetch.
    if from_cookie and request.method in CSRF_PROTECTED_METHODS:
        csrf_header = request.headers.get(CSRF_HEADER_NAME)
        csrf_claim = payload.get("csrf")
        if not csrf_header or not csrf_claim or not secrets.compare_digest(csrf_header, csrf_claim):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing or invalid CSRF token")

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
