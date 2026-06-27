from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compliance.services.issue_service import IssueService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.org_issue_settings import OrgIssueSettings
from app.models.user import User
from app.schemas.issue_settings import OrgIssueSettingsRead, OrgIssueSettingsUpdate

router = APIRouter(prefix="/compliance/issue-settings", tags=["issue-settings"])


def _read(row: OrgIssueSettings) -> OrgIssueSettingsRead:
    return OrgIssueSettingsRead(
        id=row.id,
        organization_id=row.organization_id,
        require_rca_before_close=row.require_rca_before_close,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=OrgIssueSettingsRead)
def get_org_issue_settings(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> OrgIssueSettingsRead:
    row = IssueService(db).get_org_settings(organization.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.patch("", response_model=OrgIssueSettingsRead)
def update_org_issue_settings(
    payload: OrgIssueSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:admin")),
) -> OrgIssueSettingsRead:
    row = IssueService(db).update_org_settings(
        organization.id,
        payload.require_rca_before_close,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _read(row)
