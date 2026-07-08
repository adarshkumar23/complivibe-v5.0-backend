import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_active_user,
    get_current_organization,
    get_db,
    require_org_membership,
    require_permission,
)
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_approval_request import CompliancePolicyApprovalRequest
from app.models.compliance_policy_control_link import CompliancePolicyControlLink
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.compliance_policy import (
    CompliancePolicyApprovalCancelRequest,
    CompliancePolicyApprovalDecisionRequest,
    CompliancePolicyApprovalRequestCreate,
    CompliancePolicyApprovalRequestRead,
    CompliancePolicyControlLinkCreate,
    CompliancePolicyControlLinkRead,
    CompliancePolicyControlUnlinkRequest,
    CompliancePolicyLinksSummary,
    CompliancePolicyArchiveRequest,
    CompliancePolicyCreate,
    CompliancePolicyRead,
    CompliancePolicySummary,
    CompliancePolicyUpdate,
    CompliancePolicyVersionCreate,
    CompliancePolicyVersionRead,
    CompliancePolicyVersionSubmitRequest,
)
from app.services.audit_service import AuditService
from app.services.compliance_policy_service import CompliancePolicyService
from app.services.rbac_service import RBACService
from app.compliance.services.issue_policy_link_service import IssuePolicyLinkService
from app.schemas.issue_links import PolicyAssociatedIssueRead

router = APIRouter(prefix="/compliance/policies", tags=["compliance_policies"])


def _policy_read(row: CompliancePolicy, *, violation_count: int = 0) -> CompliancePolicyRead:
    return CompliancePolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        description=row.description,
        policy_type=row.policy_type,
        status=row.status,
        owner_user_id=row.owner_user_id,
        approved_by_user_id=row.approved_by_user_id,
        approved_at=row.approved_at,
        effective_date=row.effective_date,
        review_due_date=row.review_due_date,
        version=row.version,
        content_url=row.content_url,
        tags_json=row.tags_json,
        notes=row.notes,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        archive_reason=row.archive_reason,
        violation_count=violation_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _version_read(row: CompliancePolicyVersion, *, context: dict | None = None) -> CompliancePolicyVersionRead:
    context = context or {}
    return CompliancePolicyVersionRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        version_number=row.version_number,
        content_snapshot_json=row.content_snapshot_json,
        change_summary=row.change_summary,
        status=row.status,
        submitted_by_user_id=row.submitted_by_user_id,
        submitted_at=row.submitted_at,
        reviewed_by_user_id=row.reviewed_by_user_id,
        reviewed_at=row.reviewed_at,
        review_notes=row.review_notes,
        content_sha256=row.content_sha256,
        created_at=row.created_at,
        is_live=context.get("is_live", False),
        referenced_by_active_campaign=context.get("referenced_by_active_campaign", False),
        stale_active_campaign_reference=context.get("stale_active_campaign_reference", False),
    )


def _approval_request_read(row: CompliancePolicyApprovalRequest) -> CompliancePolicyApprovalRequestRead:
    return CompliancePolicyApprovalRequestRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        version_id=row.version_id,
        requested_by_user_id=row.requested_by_user_id,
        approver_user_id=row.approver_user_id,
        status=row.status,
        notes=row.notes,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


def _require_can_decide_approval_request(
    db: Session,
    current_user: User,
    organization: Organization,
    approval_request: CompliancePolicyApprovalRequest,
) -> None:
    """Authorizes approve/reject on a specific approval request.

    Two independent, either-or paths grant authority to act on THIS request:
      1. Instance-level assignment: the caller IS approval_request.approver_user_id.
         Being named as the approver on a request is itself sufficient
         authorization for that request, regardless of the caller's role's
         blanket permission grant (e.g. a "reviewer" or "auditor" explicitly
         assigned as approver can act, even though their role does not carry
         the general compliance_policies:approve permission).
      2. Role-level override: the caller's role carries the blanket
         compliance_policies:approve permission (e.g. owner/admin), letting
         them act on any request in the org regardless of who was assigned --
         an override path, not the normal case.

    A user who is neither the assigned approver nor a blanket-permission
    holder is rejected, whether or not they are otherwise a member of the org.
    """
    is_assigned_approver = approval_request.approver_user_id == current_user.id
    has_blanket_override = RBACService.user_has_permission(
        db, current_user.id, organization.id, "compliance_policies:approve"
    )
    if not (is_assigned_approver or has_blanket_override):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned approver (or an org admin/owner) can act on this approval request",
        )


def _control_link_read(row: CompliancePolicyControlLink) -> CompliancePolicyControlLinkRead:
    return CompliancePolicyControlLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        control_id=row.control_id,
        link_reason=row.link_reason,
        status=row.status,
        linked_by_user_id=row.linked_by_user_id,
        unlinked_at=row.unlinked_at,
        unlinked_by_user_id=row.unlinked_by_user_id,
        unlink_reason=row.unlink_reason,
        created_at=row.created_at,
    )


@router.post("", response_model=CompliancePolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: CompliancePolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyRead:
    service = CompliancePolicyService(db)
    row = service.create_policy(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        policy_type=payload.policy_type,
        owner_user_id=payload.owner_user_id,
        policy_status=payload.status,
        effective_date=payload.effective_date,
        review_due_date=payload.review_due_date,
        version=payload.version,
        content_url=payload.content_url,
        tags_json=payload.tags_json,
        notes=payload.notes,
    )

    AuditService(db).write_audit_log(
        action="compliance_policy.created",
        entity_type="compliance_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "title": row.title,
            "policy_type": row.policy_type,
            "status": row.status,
            "owner_user_id": str(row.owner_user_id),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/summary", response_model=CompliancePolicySummary)
def policies_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> CompliancePolicySummary:
    return CompliancePolicySummary(**CompliancePolicyService(db).summary(organization.id))


@router.get("", response_model=list[CompliancePolicyRead])
def list_policies(
    status_filter: str | None = Query(default=None, alias="status"),
    policy_type: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None, alias="owner"),
    business_unit_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[CompliancePolicyRead]:
    stmt = select(CompliancePolicy).where(CompliancePolicy.organization_id == organization.id)

    if status_filter is not None:
        stmt = stmt.where(CompliancePolicy.status == status_filter)
    if policy_type is not None:
        stmt = stmt.where(CompliancePolicy.policy_type == policy_type)
    if owner_user_id is not None:
        stmt = stmt.where(CompliancePolicy.owner_user_id == owner_user_id)
    if business_unit_id is not None:
        stmt = stmt.where(CompliancePolicy.business_unit_id == business_unit_id)
    if not include_archived:
        stmt = stmt.where(CompliancePolicy.status != "archived")

    rows = db.execute(stmt.order_by(CompliancePolicy.created_at.desc())).scalars().all()
    violation_counts = IssuePolicyLinkService(db).get_policy_violation_counts(organization.id, [row.id for row in rows])
    return [_policy_read(row, violation_count=violation_counts.get(row.id, 0)) for row in rows]


@router.get("/{policy_id}", response_model=CompliancePolicyRead)
def get_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> CompliancePolicyRead:
    row = CompliancePolicyService(db).require_policy_in_org(organization.id, policy_id)
    violation_count = IssuePolicyLinkService(db).get_policy_violation_counts(organization.id, [row.id]).get(row.id, 0)
    return _policy_read(row, violation_count=violation_count)


@router.get("/{policy_id}/associated-issues", response_model=list[PolicyAssociatedIssueRead])
def get_policy_associated_issues(
    policy_id: uuid.UUID,
    link_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> list[PolicyAssociatedIssueRead]:
    payload = IssuePolicyLinkService(db).get_policy_associated_issues(organization.id, policy_id, link_type=link_type)
    return [PolicyAssociatedIssueRead(**row) for row in payload]


@router.patch("/{policy_id}", response_model=CompliancePolicyRead)
def update_policy(
    policy_id: uuid.UUID,
    payload: CompliancePolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyRead:
    service = CompliancePolicyService(db)
    row = service.require_policy_in_org(organization.id, policy_id)
    changes = payload.model_dump(exclude_unset=True)

    if "approved_by_user_id" in changes or "approved_at" in changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="approved_by_user_id and approved_at are managed by status transitions",
        )

    if row.status == "archived":
        disallowed = sorted([field for field in changes if field not in {"notes", "tags_json"}])
        if disallowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived policies can only update notes and tags_json",
            )

    if "owner_user_id" in changes:
        owner_user_id = changes["owner_user_id"]
        if owner_user_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="owner_user_id is required")
        service.ensure_owner_is_active_member(organization.id, owner_user_id)

    if "status" in changes:
        next_status = changes["status"]
        if next_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use archive endpoint to archive policies")

        service.validate_status_transition(row.status, next_status)
        if next_status == "approved":
            has_approve = RBACService.user_has_permission(
                db,
                current_user.id,
                organization.id,
                "compliance_policies:approve",
            )
            if not has_approve:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Missing required permission: compliance_policies:approve",
                )
            changes["approved_by_user_id"] = current_user.id
            changes["approved_at"] = service.utcnow()

    before = {
        "title": row.title,
        "policy_type": row.policy_type,
        "status": row.status,
        "owner_user_id": str(row.owner_user_id),
        "approved_by_user_id": str(row.approved_by_user_id) if row.approved_by_user_id else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }

    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy.updated",
        entity_type="compliance_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "title": row.title,
            "policy_type": row.policy_type,
            "status": row.status,
            "owner_user_id": str(row.owner_user_id),
            "approved_by_user_id": str(row.approved_by_user_id) if row.approved_by_user_id else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/{policy_id}/archive", response_model=CompliancePolicyRead)
def archive_policy(
    policy_id: uuid.UUID,
    payload: CompliancePolicyArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyRead:
    service = CompliancePolicyService(db)
    row = service.require_policy_in_org(organization.id, policy_id)

    if row.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Compliance policy is already archived")

    service.validate_status_transition(row.status, "archived")

    before = {
        "status": row.status,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        "archive_reason": row.archive_reason,
    }

    row.status = "archived"
    if row.archived_at is None:
        row.archived_at = service.utcnow()
    row.archived_by_user_id = current_user.id
    row.archive_reason = payload.reason
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy.archived",
        entity_type="compliance_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
            "archive_reason": row.archive_reason,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/{policy_id}/versions", response_model=CompliancePolicyVersionRead, status_code=status.HTTP_201_CREATED)
def create_policy_version(
    policy_id: uuid.UUID,
    payload: CompliancePolicyVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyVersionRead:
    service = CompliancePolicyService(db)
    policy = service.require_policy_in_org(organization.id, policy_id)
    if policy.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot create versions for archived policies")

    content_sha256 = service.content_sha256_hexdigest(payload.content_snapshot_json)
    row = CompliancePolicyVersion(
        organization_id=organization.id,
        policy_id=policy.id,
        version_number=payload.version_number,
        content_snapshot_json=payload.content_snapshot_json,
        change_summary=payload.change_summary,
        status="draft",
        content_sha256=content_sha256,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy_version.created",
        entity_type="compliance_policy_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(policy.id),
            "version_number": row.version_number,
            "status": row.status,
            "content_sha256": row.content_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _version_read(row)


@router.get("/{policy_id}/versions", response_model=list[CompliancePolicyVersionRead])
def list_policy_versions(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[CompliancePolicyVersionRead]:
    service = CompliancePolicyService(db)
    policy = service.require_policy_in_org(organization.id, policy_id)
    rows = db.execute(
        select(CompliancePolicyVersion)
        .where(
            CompliancePolicyVersion.organization_id == organization.id,
            CompliancePolicyVersion.policy_id == policy_id,
        )
        .order_by(CompliancePolicyVersion.created_at.desc())
    ).scalars().all()
    context = service.version_context(organization.id, policy, rows)
    return [_version_read(row, context=context.get(row.id)) for row in rows]


@router.get("/{policy_id}/versions/{version_id}", response_model=CompliancePolicyVersionRead)
def get_policy_version(
    policy_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> CompliancePolicyVersionRead:
    service = CompliancePolicyService(db)
    policy = service.require_policy_in_org(organization.id, policy_id)
    row = service.require_version_in_org(organization.id, policy_id, version_id)
    context = service.version_context(organization.id, policy, [row])
    return _version_read(row, context=context.get(row.id))


@router.post("/{policy_id}/versions/{version_id}/submit-for-approval", response_model=CompliancePolicyVersionRead)
def submit_policy_version_for_approval(
    policy_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: CompliancePolicyVersionSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyVersionRead:
    service = CompliancePolicyService(db)
    row = service.require_version_in_org(organization.id, policy_id, version_id)

    if row.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft or rejected versions can be submitted")

    row.status = "submitted"
    row.submitted_by_user_id = current_user.id
    row.submitted_at = service.utcnow()
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy_version.submitted",
        entity_type="compliance_policy_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(row.policy_id),
            "version_number": row.version_number,
            "status": row.status,
        },
        metadata_json={"source": "api", "notes": payload.notes},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _version_read(row)


@router.post("/{policy_id}/approval-requests", response_model=CompliancePolicyApprovalRequestRead, status_code=status.HTTP_201_CREATED)
def create_policy_approval_request(
    policy_id: uuid.UUID,
    payload: CompliancePolicyApprovalRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyApprovalRequestRead:
    service = CompliancePolicyService(db)
    _ = service.require_policy_in_org(organization.id, policy_id)
    version = service.require_version_in_org(organization.id, policy_id, payload.version_id)
    if version.status != "submitted":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval requests require a submitted version")

    service.ensure_active_member(organization.id, payload.approver_user_id, field_name="approver_user_id")

    row = CompliancePolicyApprovalRequest(
        organization_id=organization.id,
        policy_id=policy_id,
        version_id=payload.version_id,
        requested_by_user_id=current_user.id,
        approver_user_id=payload.approver_user_id,
        status="pending",
        notes=payload.notes,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy_approval.requested",
        entity_type="compliance_policy_approval_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(row.policy_id),
            "version_id": str(row.version_id),
            "approver_user_id": str(row.approver_user_id),
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _approval_request_read(row)


@router.get("/{policy_id}/approval-requests", response_model=list[CompliancePolicyApprovalRequestRead])
def list_policy_approval_requests(
    policy_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[CompliancePolicyApprovalRequestRead]:
    service = CompliancePolicyService(db)
    _ = service.require_policy_in_org(organization.id, policy_id)

    stmt = select(CompliancePolicyApprovalRequest).where(
        CompliancePolicyApprovalRequest.organization_id == organization.id,
        CompliancePolicyApprovalRequest.policy_id == policy_id,
    )
    if status_filter is not None:
        stmt = stmt.where(CompliancePolicyApprovalRequest.status == status_filter)

    rows = db.execute(stmt.order_by(CompliancePolicyApprovalRequest.created_at.desc())).scalars().all()
    return [_approval_request_read(row) for row in rows]


@router.post("/{policy_id}/approval-requests/{request_id}/approve", response_model=CompliancePolicyApprovalRequestRead)
def approve_policy_approval_request(
    policy_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CompliancePolicyApprovalDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_org_membership),
) -> CompliancePolicyApprovalRequestRead:
    service = CompliancePolicyService(db)
    approval_request = service.require_approval_request_in_org(organization.id, policy_id, request_id)
    if approval_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be approved")

    _require_can_decide_approval_request(db, current_user, organization, approval_request)
    if approval_request.requested_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requester cannot approve their own request")

    version = service.require_version_in_org(organization.id, policy_id, approval_request.version_id)
    policy = service.require_policy_in_org(organization.id, policy_id)
    now = service.utcnow()

    approved_rows = db.execute(
        select(CompliancePolicyVersion).where(
            CompliancePolicyVersion.organization_id == organization.id,
            CompliancePolicyVersion.policy_id == policy_id,
            CompliancePolicyVersion.status == "approved",
            CompliancePolicyVersion.id != version.id,
        )
    ).scalars().all()
    for row in approved_rows:
        row.status = "superseded"

    version.status = "approved"
    version.reviewed_by_user_id = current_user.id
    version.reviewed_at = now
    version.review_notes = payload.review_notes

    approval_request.status = "approved"
    approval_request.decided_at = now
    approval_request.notes = payload.notes if payload.notes is not None else approval_request.notes

    policy.status = "approved"
    policy.version = version.version_number
    policy.approved_by_user_id = current_user.id
    policy.approved_at = now

    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy_approval.approved",
        entity_type="compliance_policy_approval_request",
        entity_id=approval_request.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(policy.id),
            "version_id": str(version.id),
            "approval_request_status": approval_request.status,
            "version_status": version.status,
            "policy_status": policy.status,
            "superseded_version_ids": [str(row.id) for row in approved_rows],
        },
        metadata_json={"source": "api", "review_notes": payload.review_notes},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(approval_request)
    return _approval_request_read(approval_request)


@router.post("/{policy_id}/approval-requests/{request_id}/reject", response_model=CompliancePolicyApprovalRequestRead)
def reject_policy_approval_request(
    policy_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CompliancePolicyApprovalDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_org_membership),
) -> CompliancePolicyApprovalRequestRead:
    service = CompliancePolicyService(db)
    approval_request = service.require_approval_request_in_org(organization.id, policy_id, request_id)
    if approval_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be rejected")

    _require_can_decide_approval_request(db, current_user, organization, approval_request)

    version = service.require_version_in_org(organization.id, policy_id, approval_request.version_id)
    now = service.utcnow()

    approval_request.status = "rejected"
    approval_request.decided_at = now
    approval_request.notes = payload.notes if payload.notes is not None else approval_request.notes

    version.status = "rejected"
    version.reviewed_by_user_id = current_user.id
    version.reviewed_at = now
    version.review_notes = payload.review_notes

    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy_approval.rejected",
        entity_type="compliance_policy_approval_request",
        entity_id=approval_request.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(policy_id),
            "version_id": str(version.id),
            "approval_request_status": approval_request.status,
            "version_status": version.status,
        },
        metadata_json={"source": "api", "review_notes": payload.review_notes},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(approval_request)
    return _approval_request_read(approval_request)


@router.post("/{policy_id}/approval-requests/{request_id}/cancel", response_model=CompliancePolicyApprovalRequestRead)
def cancel_policy_approval_request(
    policy_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CompliancePolicyApprovalCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyApprovalRequestRead:
    service = CompliancePolicyService(db)
    approval_request = service.require_approval_request_in_org(organization.id, policy_id, request_id)
    if approval_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be cancelled")

    if approval_request.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester can cancel this request")

    approval_request.status = "cancelled"
    approval_request.decided_at = service.utcnow()
    approval_request.notes = payload.reason
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy_approval.cancelled",
        entity_type="compliance_policy_approval_request",
        entity_id=approval_request.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(policy_id),
            "version_id": str(approval_request.version_id),
            "approval_request_status": approval_request.status,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(approval_request)
    return _approval_request_read(approval_request)


@router.post("/{policy_id}/links/controls", response_model=CompliancePolicyControlLinkRead, status_code=status.HTTP_201_CREATED)
def link_control_to_policy(
    policy_id: uuid.UUID,
    payload: CompliancePolicyControlLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyControlLinkRead:
    service = CompliancePolicyService(db)
    policy = service.require_policy_in_org(organization.id, policy_id)
    if policy.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived policies cannot accept new control links")
    service.require_control_in_org(organization.id, payload.control_id)

    link = db.execute(
        select(CompliancePolicyControlLink).where(
            CompliancePolicyControlLink.organization_id == organization.id,
            CompliancePolicyControlLink.policy_id == policy_id,
            CompliancePolicyControlLink.control_id == payload.control_id,
        )
    ).scalar_one_or_none()

    if link is not None and link.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active policy-control link already exists")

    if link is None:
        link = CompliancePolicyControlLink(
            organization_id=organization.id,
            policy_id=policy_id,
            control_id=payload.control_id,
            link_reason=payload.link_reason,
            status="active",
            linked_by_user_id=current_user.id,
        )
        db.add(link)
    else:
        link.status = "active"
        link.link_reason = payload.link_reason
        link.unlinked_at = None
        link.unlinked_by_user_id = None
        link.unlink_reason = None
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy.control_linked",
        entity_type="compliance_policy_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_id": str(policy_id),
            "control_id": str(payload.control_id),
            "status": link.status,
        },
        metadata_json={"source": "api", "link_reason": payload.link_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _control_link_read(link)


@router.get("/{policy_id}/links/controls", response_model=list[CompliancePolicyControlLinkRead])
def list_policy_control_links(
    policy_id: uuid.UUID,
    include_unlinked: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[CompliancePolicyControlLinkRead]:
    service = CompliancePolicyService(db)
    _ = service.require_policy_in_org(organization.id, policy_id)
    stmt = select(CompliancePolicyControlLink).where(
        CompliancePolicyControlLink.organization_id == organization.id,
        CompliancePolicyControlLink.policy_id == policy_id,
    )
    if not include_unlinked:
        stmt = stmt.where(CompliancePolicyControlLink.status == "active")
    rows = db.execute(stmt.order_by(CompliancePolicyControlLink.created_at.desc())).scalars().all()
    return [_control_link_read(row) for row in rows]


@router.post("/{policy_id}/links/controls/{link_id}/unlink", response_model=CompliancePolicyControlLinkRead)
def unlink_control_from_policy(
    policy_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: CompliancePolicyControlUnlinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> CompliancePolicyControlLinkRead:
    service = CompliancePolicyService(db)
    _ = service.require_policy_in_org(organization.id, policy_id)
    link = db.execute(
        select(CompliancePolicyControlLink).where(
            CompliancePolicyControlLink.id == link_id,
            CompliancePolicyControlLink.organization_id == organization.id,
            CompliancePolicyControlLink.policy_id == policy_id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy-control link not found")
    if link.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy-control link is not active")

    before = {"status": link.status}
    link.status = "unlinked"
    link.unlinked_at = service.utcnow()
    link.unlinked_by_user_id = current_user.id
    link.unlink_reason = payload.unlink_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="compliance_policy.control_unlinked",
        entity_type="compliance_policy_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "policy_id": str(policy_id),
            "control_id": str(link.control_id),
            "status": link.status,
        },
        metadata_json={"source": "api", "unlink_reason": payload.unlink_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _control_link_read(link)


@router.get("/{policy_id}/links/summary", response_model=CompliancePolicyLinksSummary)
def policy_links_summary(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> CompliancePolicyLinksSummary:
    service = CompliancePolicyService(db)
    _ = service.require_policy_in_org(organization.id, policy_id)

    active_control_links = int(
        db.execute(
            select(func.count(CompliancePolicyControlLink.id)).where(
                CompliancePolicyControlLink.organization_id == organization.id,
                CompliancePolicyControlLink.policy_id == policy_id,
                CompliancePolicyControlLink.status == "active",
            )
        ).scalar_one()
    )
    unlinked_control_links = int(
        db.execute(
            select(func.count(CompliancePolicyControlLink.id)).where(
                CompliancePolicyControlLink.organization_id == organization.id,
                CompliancePolicyControlLink.policy_id == policy_id,
                CompliancePolicyControlLink.status == "unlinked",
            )
        ).scalar_one()
    )
    return CompliancePolicyLinksSummary(
        active_control_links=active_control_links,
        unlinked_control_links=unlinked_control_links,
        total_active_links=active_control_links,
        total_unlinked_links=unlinked_control_links,
    )
