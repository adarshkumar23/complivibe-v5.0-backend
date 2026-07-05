import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.non_human_identity import NonHumanIdentity
from app.models.organization import Organization
from app.models.user import User
from app.schemas.non_human_identity import (
    NonHumanIdentityCreate,
    NonHumanIdentityOrphanScanResponse,
    NonHumanIdentityRead,
    NonHumanIdentitySummary,
    NonHumanIdentityUpdate,
)
from app.services.non_human_identity_service import NonHumanIdentityService

router = APIRouter(prefix="/non-human-identities", tags=["non-human-identities"])


def _identity_read(row: NonHumanIdentity) -> NonHumanIdentityRead:
    return NonHumanIdentityRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        identity_type=row.identity_type,
        owner_user_id=row.owner_user_id,
        permissions_scope=row.permissions_scope,
        external_ref=row.external_ref,
        environment=row.environment,
        last_used_at=row.last_used_at,
        rotation_due_at=row.rotation_due_at,
        last_rotated_at=row.last_rotated_at,
        status=row.status,
        is_active=row.is_active,
        is_orphaned=row.is_orphaned,
        orphan_detected_at=row.orphan_detected_at,
        risk_level=row.risk_level,
        risk_reason=row.risk_reason,
        created_by_user_id=row.created_by_user_id,
        deleted_at=row.deleted_at,
        deleted_by_user_id=row.deleted_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _request_context(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.post("", response_model=NonHumanIdentityRead, status_code=status.HTTP_201_CREATED)
def create_identity(
    payload: NonHumanIdentityCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:manage")),
) -> NonHumanIdentityRead:
    row = NonHumanIdentityService(db).create_identity(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        data=payload.model_dump(),
        **_request_context(request),
    )
    db.commit()
    db.refresh(row)
    return _identity_read(row)


@router.get("/summary", response_model=NonHumanIdentitySummary)
def identity_summary(
    stale_days: int = Query(default=90, ge=1, le=3650),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:read")),
) -> NonHumanIdentitySummary:
    return NonHumanIdentitySummary(**NonHumanIdentityService(db).summary(organization.id, stale_days=stale_days))


@router.post("/flag-orphaned", response_model=NonHumanIdentityOrphanScanResponse)
def flag_orphaned_identities(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:manage")),
) -> NonHumanIdentityOrphanScanResponse:
    result = NonHumanIdentityService(db).flag_orphaned_identities(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        **_request_context(request),
    )
    db.commit()
    return NonHumanIdentityOrphanScanResponse(**result)


@router.get("", response_model=list[NonHumanIdentityRead])
def list_identities(
    status_filter: str | None = Query(default=None, alias="status"),
    identity_type: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None, alias="owner"),
    active_only: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:read")),
) -> list[NonHumanIdentityRead]:
    rows = NonHumanIdentityService(db).list_identities(
        organization.id,
        status_value=status_filter,
        identity_type=identity_type,
        owner_user_id=owner_user_id,
        active_only=active_only,
        include_deleted=include_deleted,
    )
    return [_identity_read(row) for row in rows]


@router.get("/{identity_id}", response_model=NonHumanIdentityRead)
def get_identity(
    identity_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:read")),
) -> NonHumanIdentityRead:
    row = NonHumanIdentityService(db).require_identity_in_org(organization.id, identity_id)
    return _identity_read(row)


@router.patch("/{identity_id}", response_model=NonHumanIdentityRead)
def update_identity(
    identity_id: uuid.UUID,
    payload: NonHumanIdentityUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:manage")),
) -> NonHumanIdentityRead:
    row = NonHumanIdentityService(db).update_identity(
        organization_id=organization.id,
        identity_id=identity_id,
        actor_user_id=current_user.id,
        changes=payload.model_dump(exclude_unset=True),
        **_request_context(request),
    )
    db.commit()
    db.refresh(row)
    return _identity_read(row)


@router.delete("/{identity_id}", response_model=NonHumanIdentityRead)
def delete_identity(
    identity_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("identity_governance:manage")),
) -> NonHumanIdentityRead:
    row = NonHumanIdentityService(db).soft_delete_identity(
        organization_id=organization.id,
        identity_id=identity_id,
        actor_user_id=current_user.id,
        **_request_context(request),
    )
    db.commit()
    db.refresh(row)
    return _identity_read(row)
