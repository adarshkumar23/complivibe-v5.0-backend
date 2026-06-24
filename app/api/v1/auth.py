import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.activation import ActivateInviteRequest, ActivateInviteResponse
from app.schemas.auth import AuthUser, CurrentUserPermissionsResponse, LoginRequest, RegisterRequest, Token
from app.services.activation_token_service import ActivationTokenService
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService
from app.services.seed_service import SeedService

router = APIRouter(prefix="/auth", tags=["auth"])


class PasswordValidationError(ValueError):
    pass


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return base[:80] or "organization"


def _generate_org_slug(db: Session, organization_name: str) -> str:
    base = _slugify(organization_name)
    candidate = base
    suffix = 1
    while db.execute(select(Organization).where(Organization.slug == candidate)).scalar_one_or_none() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise PasswordValidationError("Password must be at least 10 characters long")
    if re.search(r"[A-Z]", password) is None:
        raise PasswordValidationError("Password must include at least one uppercase letter")
    if re.search(r"[a-z]", password) is None:
        raise PasswordValidationError("Password must include at least one lowercase letter")
    if re.search(r"\d", password) is None:
        raise PasswordValidationError("Password must include at least one number")
    if re.search(r"[^A-Za-z0-9]", password) is None:
        raise PasswordValidationError("Password must include at least one symbol")


@router.post("/register", response_model=Token)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.flush()

    if payload.organization_name:
        organization = Organization(
            name=payload.organization_name,
            slug=_generate_org_slug(db, payload.organization_name),
            is_active=True,
            created_by=user.id,
        )
        db.add(organization)
        db.flush()

        roles = SeedService.ensure_roles_for_organization(db, organization.id)
        SeedService.ensure_policy_templates(db)
        owner_role = roles["owner"]

        membership = Membership(
            organization_id=organization.id,
            user_id=user.id,
            role_id=owner_role.id,
            status="active",
            invited_by=user.id,
        )
        db.add(membership)
        db.flush()

        audit_service = AuditService(db)
        audit_service.write_audit_log(
            action="organization.created",
            entity_type="organization",
            entity_id=organization.id,
            organization_id=organization.id,
            actor_user_id=user.id,
            after_json={"name": organization.name, "slug": organization.slug},
            metadata_json={"source": "register"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        audit_service.write_audit_log(
            action="membership.created",
            entity_type="membership",
            entity_id=membership.id,
            organization_id=organization.id,
            actor_user_id=user.id,
            after_json={"user_id": str(user.id), "role": "owner", "status": "active"},
            metadata_json={"source": "register"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    db.commit()

    return Token(access_token=create_access_token(subject=user.id))


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active or user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return Token(access_token=create_access_token(subject=user.id))


@router.post("/activate-invite", response_model=ActivateInviteResponse)
def activate_invite(payload: ActivateInviteRequest, db: Session = Depends(get_db)) -> ActivateInviteResponse:
    try:
        _validate_password_strength(payload.password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    token_service = ActivationTokenService(db)
    token, membership, user = token_service.consume_token_for_activation(payload.activation_token)
    before_membership_status = membership.status
    before_user_status = user.status

    user.hashed_password = get_password_hash(payload.password)
    user.status = "active"
    user.is_active = True
    if payload.full_name:
        user.full_name = payload.full_name

    membership.status = "active"

    token.status = "used"
    token.used_at = token_service.now()

    AuditService(db).write_audit_log(
        action="membership.invitation_accepted",
        entity_type="membership",
        entity_id=membership.id,
        organization_id=membership.organization_id,
        actor_user_id=user.id,
        before_json={"membership_status": before_membership_status, "user_status": before_user_status},
        after_json={"membership_status": membership.status, "user_status": user.status},
        metadata_json={"source": "activation"},
    )

    db.commit()
    return ActivateInviteResponse(message="Invitation activated successfully. Please log in.")


@router.get("/me", response_model=AuthUser)
def me(current_user: User = Depends(get_current_active_user)) -> AuthUser:
    return AuthUser.model_validate(current_user)


@router.get("/permissions", response_model=CurrentUserPermissionsResponse)
def current_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> CurrentUserPermissionsResponse:
    permission_codes = sorted(RBACService.get_user_permissions(db, current_user.id, organization.id))
    return CurrentUserPermissionsResponse(organization_id=organization.id, permission_codes=permission_codes)
