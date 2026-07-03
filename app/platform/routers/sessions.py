from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_org_membership, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.user_session import UserSession
from app.platform.services.session_service import SessionService
from app.schemas.session_management import UserSessionRead
from app.services.rbac_service import RBACService

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[UserSessionRead])
def list_my_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_org_membership),
) -> list[UserSessionRead]:
    rows = SessionService(db).list_sessions(org_id=organization.id, user_id=current_user.id)
    return [UserSessionRead.model_validate(row) for row in rows]


@router.delete("/sessions/{session_id}", response_model=UserSessionRead)
def revoke_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_org_membership),
) -> UserSessionRead:
    row = db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    is_admin = RBACService.user_has_permission(db, current_user.id, membership.organization_id, "org:update")
    if row.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot revoke another user's session")

    updated = SessionService(db).revoke_session(org_id=organization.id, session_id=session_id, revoked_by=current_user.id)
    db.commit()
    db.refresh(updated)
    return UserSessionRead.model_validate(updated)


@router.get("/organizations/users/{user_id}/sessions", response_model=list[UserSessionRead])
def list_user_sessions_for_org(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> list[UserSessionRead]:
    in_org = db.execute(
        select(Membership.id).where(
            Membership.organization_id == organization.id,
            Membership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if in_org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    rows = SessionService(db).list_sessions(org_id=organization.id, user_id=user_id)
    return [UserSessionRead.model_validate(row) for row in rows]
