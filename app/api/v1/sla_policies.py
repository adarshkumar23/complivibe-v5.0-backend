from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compliance.services.sla_service import SLAService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.issue_sla_policy import IssueSLAPolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.sla import (
    IssueSLAPolicyRead,
    IssueSLAPolicyUpsertRequest,
    SLABreachCheckResult,
)

router = APIRouter(prefix="/compliance/sla-policies", tags=["issue-sla-policies"])


def _read(row: IssueSLAPolicy) -> IssueSLAPolicyRead:
    return IssueSLAPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        severity=row.severity,
        response_sla_hours=row.response_sla_hours,
        resolution_sla_hours=row.resolution_sla_hours,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[IssueSLAPolicyRead])
def list_sla_policies(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[IssueSLAPolicyRead]:
    service = SLAService(db)
    service.ensure_default_policies(organization.id)
    db.flush()
    rows = service.get_sla_policies(organization.id)
    return [_read(row) for row in rows]


@router.post("", response_model=IssueSLAPolicyRead)
def create_or_update_sla_policy(
    payload: IssueSLAPolicyUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:write")),
) -> IssueSLAPolicyRead:
    row = SLAService(db).create_or_update_sla_policy(
        organization.id,
        payload.severity,
        payload.response_hours,
        payload.resolution_hours,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("/trigger-breach-check", response_model=SLABreachCheckResult)
def trigger_breach_check(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    __: Membership = Depends(require_permission("issues:admin")),
) -> SLABreachCheckResult:
    payload = SLAService(db).check_sla_breaches(organization.id)
    db.commit()
    return SLABreachCheckResult(**payload)
