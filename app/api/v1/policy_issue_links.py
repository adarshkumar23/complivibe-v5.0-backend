import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.issue_policy_link_service import IssuePolicyLinkService as FormalIssuePolicyLinkService
from app.compliance.services.issue_service import IssueService
from app.compliance.services.policy_issue_link_service import PolicyIssueLinkService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.schemas.policy_issue_link import (
    IssuePolicyContextResponse,
    PolicyEffectivenessResponse,
    PolicyIssueIssueRef,
    PolicyIssueLinkResponse,
    PolicyIssuePolicyRef,
)

router = APIRouter(prefix="/compliance", tags=["policy-issue-links"])

# --------------------------------------------------------------------------
# Deprecation notice
# --------------------------------------------------------------------------
#
# This v1 policy-issue-links surface is built on the ``policy_issue_links``
# table, whose ``issue_id`` column has a hard foreign key to ``tasks.id``
# (see migration 0103). Real, user-facing issues created via
# ``/compliance/issues`` live in the separate ``issues`` table (the ``Issue``
# model) -- a different table with a disjoint UUID space. Because of that,
# every v1 endpoint that resolves ``issue_id`` against ``tasks`` returns a
# misleading "Issue not found" 404 for any issue actually created through the
# real issues feature; it can only ever "see" the legacy Task-backed
# issue concept.
#
# ``/compliance/policies/{policy_id}/issues`` (see
# ``app/compliance/routers/policy_issue_links.py``, tag
# ``policy-issue-links-v2``) is the correct, Issue-model-backed replacement
# and is fully functional. Rather than leave this broken parallel path
# silently live returning a confusing "not found" for perfectly real issues,
# every endpoint below that depends on a Task-backed issue lookup now returns
# a clear 410 Gone pointing callers at the v2 endpoint to use instead.
#
# The one exception is ``GET /issues/{issue_id}/policy-links`` -- it already
# falls back to the v2 (Issue-model-backed) data source when the issue isn't
# a Task, so it works correctly for real issues today and is left as-is.

_DEPRECATION_DETAIL = (
    "This v1 policy-issue-links endpoint is deprecated and no longer usable: it only "
    "resolves issue_id against the legacy Task-backed issue concept, so it cannot see "
    "issues created via /compliance/issues. Use {replacement} instead."
)


def _deprecated(replacement: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=_DEPRECATION_DETAIL.format(replacement=replacement),
    )


@router.post("/policy-issue-links", response_model=PolicyIssueLinkResponse, status_code=status.HTTP_201_CREATED)
def create_policy_issue_link() -> PolicyIssueLinkResponse:
    _deprecated("POST /compliance/policies/{policy_id}/issues")


@router.get("/policy-issue-links/summary")
def get_org_policy_issue_link_summary() -> None:
    _deprecated("GET /compliance/policies/{policy_id}/violation-rate")


@router.get("/policy-issue-links", response_model=list[PolicyIssueLinkResponse])
def list_policy_issue_links() -> list[PolicyIssueLinkResponse]:
    _deprecated("GET /compliance/policies/{policy_id}/issues or GET /compliance/issues/{issue_id}/policies")


@router.get("/policy-issue-links/{link_id}", response_model=PolicyIssueLinkResponse)
def get_policy_issue_link(link_id: uuid.UUID) -> PolicyIssueLinkResponse:
    _deprecated("GET /compliance/policies/{policy_id}/issues or GET /compliance/issues/{issue_id}/policies")


@router.patch("/policy-issue-links/{link_id}", response_model=PolicyIssueLinkResponse)
def update_policy_issue_link(link_id: uuid.UUID) -> PolicyIssueLinkResponse:
    _deprecated(
        "unlink and relink via DELETE and POST /compliance/policies/{policy_id}/issues/{issue_id}"
    )


@router.delete("/policy-issue-links/{link_id}", response_model=PolicyIssueLinkResponse)
def delete_policy_issue_link(link_id: uuid.UUID) -> PolicyIssueLinkResponse:
    _deprecated("DELETE /compliance/policies/{policy_id}/issues/{issue_id}")


@router.get("/policies/{policy_id}/issue-links", response_model=list[PolicyIssueLinkResponse])
def list_policy_issue_links_for_policy(policy_id: uuid.UUID) -> list[PolicyIssueLinkResponse]:
    _deprecated("GET /compliance/policies/{policy_id}/issues")


@router.get("/policies/{policy_id}/effectiveness", response_model=PolicyEffectivenessResponse)
def get_policy_effectiveness(policy_id: uuid.UUID) -> PolicyEffectivenessResponse:
    _deprecated("GET /compliance/policies/{policy_id}/violation-rate")


@router.get("/issues/{issue_id}/policy-links", response_model=list[PolicyIssueLinkResponse])
def list_policy_issue_links_for_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_issues:view")),
) -> list[PolicyIssueLinkResponse]:
    service = PolicyIssueLinkService(db)
    try:
        issue = service.require_issue_in_org(organization.id, issue_id)
        rows = service.list_links_for_issue(organization.id, issue_id)
        return [
            PolicyIssueLinkResponse(
                id=link.id,
                organization_id=link.organization_id,
                policy_id=link.policy_id,
                issue_id=link.issue_id,
                violation_type=link.violation_type,
                severity_impact=link.severity_impact,
                notes=link.notes,
                linked_by=link.linked_by,
                created_at=link.created_at,
                updated_at=link.updated_at,
                policy=PolicyIssuePolicyRef(id=policy.id, name=policy.title) if policy else None,
                issue=PolicyIssueIssueRef(
                    id=issue.id,
                    title=issue.title,
                    status=issue.status,
                    severity=service.issue_severity(issue),
                ),
            )
            for link, policy in rows
        ]
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise

    formal_rows = FormalIssuePolicyLinkService(db).get_issue_policy_links(organization.id, issue_id)
    formal_issue = IssueService(db).get_issue(organization.id, issue_id)

    if not formal_rows:
        return []

    policy_ids = [row.policy_id for row in formal_rows]
    policies = db.execute(
        select(CompliancePolicy).where(
            CompliancePolicy.organization_id == organization.id,
            CompliancePolicy.id.in_(policy_ids),
        )
    ).scalars().all()
    policy_by_id = {row.id: row for row in policies}

    violation_type_map = {"violated": "violation", "related": "observation"}
    payload: list[PolicyIssueLinkResponse] = []
    for row in formal_rows:
        policy = policy_by_id.get(row.policy_id)
        payload.append(
            PolicyIssueLinkResponse(
                id=row.id,
                organization_id=row.organization_id,
                policy_id=row.policy_id,
                issue_id=row.issue_id,
                violation_type=violation_type_map.get(row.link_type, "observation"),
                severity_impact=formal_issue.severity if formal_issue.severity in {"low", "medium", "high", "critical"} else "medium",
                notes=None,
                linked_by=row.linked_by,
                created_at=row.linked_at,
                updated_at=row.linked_at,
                policy=PolicyIssuePolicyRef(id=policy.id, name=policy.title) if policy is not None else None,
                issue=PolicyIssueIssueRef(
                    id=formal_issue.id,
                    title=formal_issue.title,
                    status=formal_issue.status,
                    severity=formal_issue.severity,
                ),
            )
        )
    return payload


@router.get("/issues/{issue_id}/policy-context", response_model=IssuePolicyContextResponse)
def get_issue_policy_context(issue_id: uuid.UUID) -> IssuePolicyContextResponse:
    _deprecated("GET /compliance/issues/{issue_id}/policies")
