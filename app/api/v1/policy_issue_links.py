import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.policy_issue_link_service import PolicyIssueLinkService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.policy_issue_link import PolicyIssueLink
from app.models.task import Task
from app.models.user import User
from app.schemas.policy_issue_link import (
    IssuePolicyContextResponse,
    OrgPolicyEffectivenessSummaryResponse,
    PolicyEffectivenessResponse,
    PolicyIssueIssueRef,
    PolicyIssueLinkCreate,
    PolicyIssueLinkResponse,
    PolicyIssueLinkUpdate,
    PolicyIssuePolicyRef,
)

router = APIRouter(prefix="/compliance", tags=["policy-issue-links"])


def _link_read(
    row: PolicyIssueLink,
    *,
    policy: CompliancePolicy | None = None,
    issue: Task | None = None,
    service: PolicyIssueLinkService,
) -> PolicyIssueLinkResponse:
    return PolicyIssueLinkResponse(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        issue_id=row.issue_id,
        violation_type=row.violation_type,
        severity_impact=row.severity_impact,
        notes=row.notes,
        linked_by=row.linked_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        policy=PolicyIssuePolicyRef(id=policy.id, name=policy.title) if policy else None,
        issue=(
            PolicyIssueIssueRef(
                id=issue.id,
                title=issue.title,
                status=issue.status,
                severity=service.issue_severity(issue),
            )
            if issue
            else None
        ),
    )


@router.post("/policy-issue-links", response_model=PolicyIssueLinkResponse, status_code=status.HTTP_201_CREATED)
def create_policy_issue_link(
    payload: PolicyIssueLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:manage")),
) -> PolicyIssueLinkResponse:
    service = PolicyIssueLinkService(db)
    row = service.create_link(
        organization.id,
        payload.policy_id,
        payload.issue_id,
        payload.violation_type,
        payload.severity_impact,
        payload.notes,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    policy = service.require_policy_in_org(organization.id, row.policy_id)
    issue = service.require_issue_in_org(organization.id, row.issue_id)
    return _link_read(row, policy=policy, issue=issue, service=service)


@router.get("/policy-issue-links/summary", response_model=OrgPolicyEffectivenessSummaryResponse)
def get_org_policy_issue_link_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> OrgPolicyEffectivenessSummaryResponse:
    payload = PolicyIssueLinkService(db).get_org_policy_effectiveness_summary(organization.id)
    return OrgPolicyEffectivenessSummaryResponse(**payload)


@router.get("/policy-issue-links", response_model=list[PolicyIssueLinkResponse])
def list_policy_issue_links(
    policy_id: uuid.UUID | None = Query(default=None),
    issue_id: uuid.UUID | None = Query(default=None),
    violation_type: str | None = Query(default=None),
    severity_impact: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> list[PolicyIssueLinkResponse]:
    service = PolicyIssueLinkService(db)
    rows = service.list_links(
        organization.id,
        policy_id=policy_id,
        issue_id=issue_id,
        violation_type=violation_type,
        severity_impact=severity_impact,
    )
    return [_link_read(link, policy=policy, issue=issue, service=service) for link, policy, issue in rows]


@router.get("/policy-issue-links/{link_id}", response_model=PolicyIssueLinkResponse)
def get_policy_issue_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> PolicyIssueLinkResponse:
    service = PolicyIssueLinkService(db)
    link, policy, issue = service.get_link(organization.id, link_id)
    return _link_read(link, policy=policy, issue=issue, service=service)


@router.patch("/policy-issue-links/{link_id}", response_model=PolicyIssueLinkResponse)
def update_policy_issue_link(
    link_id: uuid.UUID,
    payload: PolicyIssueLinkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:manage")),
) -> PolicyIssueLinkResponse:
    service = PolicyIssueLinkService(db)
    link = service.update_link(organization.id, link_id, payload, current_user.id)
    db.commit()
    db.refresh(link)
    policy = service.require_policy_in_org(organization.id, link.policy_id)
    issue = service.require_issue_in_org(organization.id, link.issue_id)
    return _link_read(link, policy=policy, issue=issue, service=service)


@router.delete("/policy-issue-links/{link_id}", response_model=PolicyIssueLinkResponse)
def delete_policy_issue_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:manage")),
) -> PolicyIssueLinkResponse:
    service = PolicyIssueLinkService(db)
    row = service.delete_link(organization.id, link_id, current_user.id)
    db.commit()
    policy = service.require_policy_in_org(organization.id, row.policy_id)
    issue = service.require_issue_in_org(organization.id, row.issue_id)
    return _link_read(row, policy=policy, issue=issue, service=service)


@router.get("/policies/{policy_id}/issue-links", response_model=list[PolicyIssueLinkResponse])
def list_policy_issue_links_for_policy(
    policy_id: uuid.UUID,
    violation_type: str | None = Query(default=None),
    severity_impact: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> list[PolicyIssueLinkResponse]:
    service = PolicyIssueLinkService(db)
    policy = service.require_policy_in_org(organization.id, policy_id)
    rows = service.list_links_for_policy(
        organization.id,
        policy_id,
        violation_type=violation_type,
        severity_impact=severity_impact,
    )
    return [_link_read(link, policy=policy, issue=issue, service=service) for link, issue in rows]


@router.get("/policies/{policy_id}/effectiveness", response_model=PolicyEffectivenessResponse)
def get_policy_effectiveness(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> PolicyEffectivenessResponse:
    payload = PolicyIssueLinkService(db).get_policy_effectiveness(organization.id, policy_id)
    return PolicyEffectivenessResponse(**payload)


@router.get("/issues/{issue_id}/policy-links", response_model=list[PolicyIssueLinkResponse])
def list_policy_issue_links_for_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> list[PolicyIssueLinkResponse]:
    service = PolicyIssueLinkService(db)
    issue = service.require_issue_in_org(organization.id, issue_id)
    rows = service.list_links_for_issue(organization.id, issue_id)
    return [_link_read(link, policy=policy, issue=issue, service=service) for link, policy in rows]


@router.get("/issues/{issue_id}/policy-context", response_model=IssuePolicyContextResponse)
def get_issue_policy_context(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> IssuePolicyContextResponse:
    payload = PolicyIssueLinkService(db).get_issue_policy_context(organization.id, issue_id)
    return IssuePolicyContextResponse(**payload)
