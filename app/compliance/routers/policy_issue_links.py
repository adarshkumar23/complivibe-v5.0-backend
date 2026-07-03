import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.schemas.policy_issue_links import (
    PolicyIssueLinkCreateRequest,
    PolicyIssueLinkResponse,
    PolicyIssueRef,
    PolicyRef,
)
from app.compliance.services.policy_issue_link_service import PolicyIssueLinkService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance", tags=["policy-issue-links-v2"])


@router.post("/policies/{policy_id}/issues", response_model=PolicyIssueLinkResponse, status_code=status.HTTP_201_CREATED)
def link_issue_to_policy(
    policy_id: uuid.UUID,
    payload: PolicyIssueLinkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyIssueLinkResponse:
    row = PolicyIssueLinkService(db).link_issue(
        org_id=organization.id,
        policy_id=policy_id,
        issue_id=payload.issue_id,
        created_by=current_user.id,
        link_reason=payload.link_reason,
    )
    db.commit()
    db.refresh(row)
    return PolicyIssueLinkResponse(
        issue_id=row.issue_id,
        policy_id=row.policy_id,
        status=row.status,
        link_reason=row.link_reason,
    )


@router.delete("/policies/{policy_id}/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_issue_from_policy(
    policy_id: uuid.UUID,
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> None:
    PolicyIssueLinkService(db).unlink_issue(
        org_id=organization.id,
        policy_id=policy_id,
        issue_id=issue_id,
        unlinked_by=current_user.id,
    )
    db.commit()
    return None


@router.get("/policies/{policy_id}/issues", response_model=list[PolicyIssueRef])
def list_issues_for_policy(
    policy_id: uuid.UUID,
    include_resolved: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[PolicyIssueRef]:
    rows = PolicyIssueLinkService(db).list_issues_for_policy(
        org_id=organization.id,
        policy_id=policy_id,
        include_resolved=include_resolved,
    )
    return [
        PolicyIssueRef(
            id=row.id,
            title=row.title,
            status=row.status,
            severity=row.severity,
            issue_type=row.issue_type,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/issues/{issue_id}/policies", response_model=list[PolicyRef])
def list_policies_for_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[PolicyRef]:
    rows = PolicyIssueLinkService(db).list_policies_for_issue(org_id=organization.id, issue_id=issue_id)
    return [PolicyRef(id=row.id, title=row.title, status=row.status) for row in rows]


@router.get("/policies/{policy_id}/violation-rate", response_model=dict)
def get_policy_violation_rate(
    policy_id: uuid.UUID,
    lookback_days: int = Query(default=365, ge=1, le=3650),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> dict:
    return PolicyIssueLinkService(db).get_policy_violation_rate(
        org_id=organization.id,
        policy_id=policy_id,
        lookback_days=lookback_days,
    )
