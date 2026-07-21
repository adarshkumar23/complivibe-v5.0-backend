import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.repositories.membership_repository import MembershipRepository
from app.schemas.activation import (
    ActivationTokenCreateResponse,
    ActivationTokenRevokeResponse,
    ActivationTokenStatusResponse,
)
from app.schemas.membership import (
    MembershipCreate,
    MembershipDeactivateResponse,
    MembershipRead,
    MembershipRoleUpdate,
    MembershipUserRead,
)
from app.services.activation_token_service import ActivationTokenService
from app.services.audit_service import AuditService
from app.services.non_human_identity_service import NonHumanIdentityService
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/memberships", tags=["memberships"])


def _resolve_role(db: Session, organization_id: uuid.UUID, role_id: uuid.UUID | None, role_name: str | None):
    if role_id is None and role_name is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either role_id or role_name is required")
    if role_id is not None and role_name is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either role_id or role_name, not both")

    role = (
        RBACService.get_role_by_id(db, role_id)
        if role_id is not None
        else RBACService.get_role_by_name(db, organization_id, role_name or "")
    )
    if role is None or role.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found in organization")
    return role


def _membership_read(db: Session, membership: Membership, role_name: str | None = None) -> MembershipRead:
    user = db.execute(select(User).where(User.id == membership.user_id)).scalar_one()
    if role_name is None:
        role = RBACService.get_role_by_id(db, membership.role_id)
        role_name = role.name if role else "unknown"

    return MembershipRead(
        id=membership.id,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        role_id=membership.role_id,
        role_name=role_name,
        status=membership.status,
        invited_by=membership.invited_by,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
        user=MembershipUserRead(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            is_active=user.is_active,
        ),
    )


def _load_org_membership_or_404(db: Session, organization_id: uuid.UUID, membership_id: uuid.UUID) -> Membership:
    membership = MembershipRepository(db).get_by_id(membership_id)
    if membership is None or membership.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    return membership


def _ensure_invite_or_update_role_permission(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if RBACService.user_has_permission(db, user_id, organization_id, "users:invite"):
        return
    if RBACService.user_has_permission(db, user_id, organization_id, "users:update_role"):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission")


@router.get("", response_model=list[MembershipRead])
def list_memberships(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:read")),
) -> list[MembershipRead]:
    memberships = MembershipRepository(db).list_by_organization(organization.id)
    return [_membership_read(db, membership) for membership in memberships]


@router.get("/{membership_id}", response_model=MembershipRead)
def get_membership(
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:read")),
) -> MembershipRead:
    membership = _load_org_membership_or_404(db, organization.id, membership_id)
    return _membership_read(db, membership)


@router.post("", response_model=MembershipRead, status_code=status.HTTP_201_CREATED)
def create_membership(
    payload: MembershipCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:invite")),
) -> MembershipRead:
    role = _resolve_role(db, organization.id, payload.role_id, payload.role_name)
    repo = MembershipRepository(db)

    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    # The system account's memberships are managed by SystemAccountService, lazily and
    # with a zero-permission role. Inviting it here would hand it whatever role the
    # caller picked and surface it as a colleague.
    if user is not None and user.is_system_account:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That address belongs to a system account and cannot be invited",
        )
    action = "membership.created"
    if user is None:
        temp_password = secrets.token_urlsafe(32)
        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(temp_password),
            status="invited",
            is_active=False,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        action = "user.invited"
    elif payload.full_name and not user.full_name:
        user.full_name = payload.full_name

    existing_membership = repo.get_by_user_and_org(user.id, organization.id)
    if existing_membership is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member of this organization")

    membership_status = payload.status or ("active" if user.is_active and user.status == "active" else "invited")

    membership = repo.create(
        organization_id=organization.id,
        user_id=user.id,
        role_id=role.id,
        status=membership_status,
        invited_by=current_user.id,
    )

    audit = AuditService(db)
    audit.write_audit_log(
        action=action,
        entity_type="membership",
        entity_id=membership.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "user_id": str(user.id),
            "email": user.email,
            "role": role.name,
            "status": membership.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(membership)
    return _membership_read(db, membership, role_name=role.name)


@router.patch("/{membership_id}/role", response_model=MembershipRead)
def update_membership_role(
    membership_id: uuid.UUID,
    payload: MembershipRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:update_role")),
) -> MembershipRead:
    membership = _load_org_membership_or_404(db, organization.id, membership_id)

    role_before = RBACService.get_role_by_id(db, membership.role_id)
    new_role = _resolve_role(db, organization.id, payload.role_id, payload.role_name)

    RBACService.assert_not_last_owner_change(
        db,
        target_membership=membership,
        organization_id=organization.id,
        new_role_name=new_role.name,
    )

    before = {
        "role_id": str(membership.role_id),
        "role_name": role_before.name if role_before else None,
        "status": membership.status,
    }

    membership.role_id = new_role.id
    db.flush()

    after = {"role_id": str(new_role.id), "role_name": new_role.name, "status": membership.status}

    AuditService(db).write_audit_log(
        action="membership.role_updated",
        entity_type="membership",
        entity_id=membership.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json=after,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(membership)
    return _membership_read(db, membership, role_name=new_role.name)


@router.patch("/{membership_id}/deactivate", response_model=MembershipDeactivateResponse)
def deactivate_membership(
    membership_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:update_role")),
) -> MembershipDeactivateResponse:
    membership = _load_org_membership_or_404(db, organization.id, membership_id)

    RBACService.assert_not_last_owner_change(
        db,
        target_membership=membership,
        organization_id=organization.id,
        deactivating=True,
    )

    before = {"status": membership.status}
    membership.status = "inactive"

    token_service = ActivationTokenService(db)
    token_service.revoke_active_tokens_for_membership(membership.id)
    db.flush()

    AuditService(db).write_audit_log(
        action="membership.deactivated",
        entity_type="membership",
        entity_id=membership.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": membership.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # BUG (NHI orphan detection never fires via real offboarding): flag_orphaned_identities
    # (NonHumanIdentityService) is logically correct in isolation -- it joins each
    # NonHumanIdentity.owner_user_id to its User and flags the identity as orphaned once
    # that owner is no longer active -- but nothing in the real offboarding path ever
    # invoked it, so a deactivated member's service accounts/API keys/NHIs were only ever
    # discovered by someone separately hitting the orphan-scan endpoint, if ever. Run the
    # scan for this organization as part of the same deactivation transaction so an
    # offboarded member's orphaned NHIs are detected and flagged immediately, not silently.
    nhi_scan_result = NonHumanIdentityService(db).flag_orphaned_identities(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return MembershipDeactivateResponse(
        membership_id=membership.id,
        status=membership.status,
        detail="Membership deactivated",
        non_human_identities_scanned=nhi_scan_result["identities_scanned"],
        non_human_identities_orphaned_flagged=nhi_scan_result["orphaned_flagged"],
    )


@router.post("/{membership_id}/activation-token", response_model=ActivationTokenCreateResponse)
def create_activation_token(
    membership_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:invite")),
) -> ActivationTokenCreateResponse:
    membership = MembershipRepository(db).get_by_id(membership_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    if membership.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership does not belong to active organization")
    if membership.status == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot issue token for inactive membership")

    user = db.execute(select(User).where(User.id == membership.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership user not found")

    token_service = ActivationTokenService(db)
    token, raw_token = token_service.create_token(
        membership=membership,
        user=user,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="membership.activation_token_created",
        entity_type="membership_activation_token",
        entity_id=token.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "membership_id": str(membership.id),
            "user_id": str(user.id),
            "expires_at": token.expires_at.isoformat(),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()

    return ActivationTokenCreateResponse(
        membership_id=membership.id,
        user_id=user.id,
        expires_at=token.expires_at,
        activation_token=raw_token,
        warning="Token is shown only once. Store it securely.",
    )


@router.post("/{membership_id}/activation-token/revoke", response_model=ActivationTokenRevokeResponse)
def revoke_activation_token(
    membership_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:read")),
) -> ActivationTokenRevokeResponse:
    _ensure_invite_or_update_role_permission(db, current_user.id, organization.id)

    membership = _load_org_membership_or_404(db, organization.id, membership_id)
    token_service = ActivationTokenService(db)
    revoked_count = token_service.revoke_active_tokens_for_membership(membership.id)

    AuditService(db).write_audit_log(
        action="membership.activation_token_revoked",
        entity_type="membership",
        entity_id=membership.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"revoked_count": revoked_count},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return ActivationTokenRevokeResponse(
        membership_id=membership.id,
        revoked_count=revoked_count,
        detail="Activation tokens revoked",
    )


@router.get("/{membership_id}/activation-token/status", response_model=ActivationTokenStatusResponse)
def activation_token_status(
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("users:read")),
) -> ActivationTokenStatusResponse:
    membership = _load_org_membership_or_404(db, organization.id, membership_id)
    token_service = ActivationTokenService(db)
    has_active, token = token_service.get_active_status(membership.id)

    return ActivationTokenStatusResponse(
        membership_id=membership.id,
        has_active_token=has_active,
        status=token.status if token else None,
        expires_at=token.expires_at if token else None,
    )
