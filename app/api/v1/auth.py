import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.core.password_validation import PasswordValidationError, validate_password_strength
from app.core.rate_limiter import rate_limiter
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.activation import ActivateInviteRequest, ActivateInviteResponse
from app.schemas.auth import AuthUser, CurrentUserPermissionsResponse, LoginRequest, RegisterRequest, Token
from app.services.activation_token_service import ActivationTokenService
from app.services.audit_service import AuditService
from app.platform.services.billing_service import BillingService
from app.platform.services.ip_allowlist_service import IPAllowlistService
from app.platform.services.session_service import SessionService
from app.services.rbac_service import RBACService
from app.services.seed_service import SeedService

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post("/register", response_model=Token)
@rate_limiter.limiter.limit("10/minute")
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    try:
        validate_password_strength(payload.password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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
        SeedService.ensure_questionnaire_scoring_rules(db)
        SeedService.ensure_issue_sla_policies(db, organization.id)
        SeedService.ensure_default_data_access_anomaly_rules(db, organization.id, user.id)
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
        BillingService(db).start_trial(organization.id)

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
@rate_limiter.limiter.limit("10/minute")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active or user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    requested_org_id: uuid.UUID | None = None
    org_header = request.headers.get("X-Organization-ID")
    if org_header:
        try:
            requested_org_id = uuid.UUID(org_header)
        except ValueError:
            requested_org_id = None

    session_service = SessionService(db)
    session_org_id = session_service.resolve_login_org_id(user.id, requested_org_id)
    if session_org_id is None:
        # Keep compatibility for users with no active membership by issuing a legacy stateless token.
        return Token(access_token=create_access_token(subject=user.id))

    token_id = str(uuid.uuid4())
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(subject=user.id, extra={"jti": token_id})
    session_service.create_session(
        org_id=session_org_id,
        user_id=user.id,
        token_id=token_id,
        ip_address=IPAllowlistService.extract_request_ip(
            x_forwarded_for=request.headers.get("X-Forwarded-For"),
            client_host=request.client.host if request.client else None,
        ),
        user_agent=request.headers.get("user-agent"),
        expires_at=expires_at,
    )
    db.commit()
    return Token(access_token=access_token)


@router.post("/activate-invite", response_model=ActivateInviteResponse)
@rate_limiter.limiter.limit("10/minute")
def activate_invite(payload: ActivateInviteRequest, request: Request, db: Session = Depends(get_db)) -> ActivateInviteResponse:
    try:
        validate_password_strength(payload.password)
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
