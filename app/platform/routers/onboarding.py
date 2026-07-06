from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_active_user,
    get_current_organization,
    get_db,
    require_org_membership,
    require_permission,
)
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.platform.schemas.onboarding import (
    AcceptInviteRequest,
    FrameworkSelectionRequest,
    OnboardingChecklistResponse,
    OnboardingStartRequest,
    OnboardingStartResponse,
    TeamInviteRequest,
    TeamInvitationAcceptResponse,
    TeamInvitationRead,
    TeamInvitationRevokeResponse,
)
from app.schemas.pricing import OnboardingSelectPlanRead
from app.platform.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _require_admin_membership(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


@router.post("/start", response_model=OnboardingStartResponse)
@rate_limiter.limiter.limit("10/minute")
def start_onboarding(payload: OnboardingStartRequest, request: Request, db: Session = Depends(get_db)) -> OnboardingStartResponse:
    result = OnboardingService().start_onboarding(
        org_name=payload.org_name,
        org_slug=payload.org_slug,
        admin_email=payload.admin_email,
        admin_full_name=payload.admin_full_name,
        admin_password=payload.admin_password,
        db=db,
    )
    db.commit()
    return OnboardingStartResponse(**result)


@router.get("/check-slug")
def check_slug(slug: str, db: Session = Depends(get_db)) -> dict:
    normalized = OnboardingService._slugify(slug)
    existing = db.execute(select(Organization).where(Organization.slug == normalized)).scalar_one_or_none()
    return {"available": existing is None}


@router.get("/select-plan", response_model=OnboardingSelectPlanRead)
def select_plan_options(db: Session = Depends(get_db)) -> OnboardingSelectPlanRead:
    payload = OnboardingService().select_plan_options(db=db)
    db.commit()
    return OnboardingSelectPlanRead(**payload)


@router.post("/accept-invite", response_model=TeamInvitationAcceptResponse)
def accept_invite(payload: AcceptInviteRequest, db: Session = Depends(get_db)) -> TeamInvitationAcceptResponse:
    result = OnboardingService().accept_invitation(
        token=payload.token,
        full_name=payload.full_name,
        password=payload.password,
        db=db,
    )
    db.commit()
    return TeamInvitationAcceptResponse(**result)


@router.post("/select-frameworks")
def select_frameworks(
    payload: FrameworkSelectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> dict:
    _require_admin_membership(db, membership)
    result = OnboardingService().select_frameworks(
        org_id=organization.id,
        framework_ids=payload.framework_ids,
        user_id=current_user.id,
        db=db,
    )
    db.commit()
    return result


@router.post("/invite-team")
def invite_team(
    payload: TeamInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> dict:
    _require_admin_membership(db, membership)
    result = OnboardingService().invite_team_members(
        org_id=organization.id,
        invites=[item.model_dump() for item in payload.invites],
        invited_by=current_user.id,
        db=db,
    )
    db.commit()
    return result


@router.get("/checklist", response_model=OnboardingChecklistResponse)
def checklist(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_org_membership),
) -> OnboardingChecklistResponse:
    result = OnboardingService().get_checklist(org_id=organization.id, db=db)
    return OnboardingChecklistResponse(**result)


@router.post("/complete")
def complete_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> dict:
    _require_admin_membership(db, membership)
    result = OnboardingService().complete_onboarding(org_id=organization.id, user_id=current_user.id, db=db)
    db.commit()
    return result


@router.get("/team-invitations", response_model=list[TeamInvitationRead])
def list_team_invitations(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:read")),
) -> list[TeamInvitationRead]:
    _require_admin_membership(db, membership)
    rows = OnboardingService().list_team_invitations(org_id=organization.id, db=db)
    return [TeamInvitationRead.model_validate(row) for row in rows]


@router.delete("/team-invitations/{invitation_id}", response_model=TeamInvitationRevokeResponse)
def revoke_team_invitation(
    invitation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> TeamInvitationRevokeResponse:
    _require_admin_membership(db, membership)
    row = OnboardingService().revoke_invitation(
        org_id=organization.id,
        invitation_id=invitation_id,
        user_id=current_user.id,
        db=db,
    )
    db.commit()
    return TeamInvitationRevokeResponse(id=row.id, status=row.status)
