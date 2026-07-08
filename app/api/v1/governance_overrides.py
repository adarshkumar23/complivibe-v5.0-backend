import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.governance_override_approval import GovernanceOverrideApproval
from app.models.governance_override_event import GovernanceOverrideEvent
from app.models.governance_override_request import GovernanceOverrideRequest
from app.models.organization import Organization
from app.models.user import User
from app.repositories.governance_override_repository import GovernanceOverrideRepository
from app.schemas.governance_override import (
    GovernanceOverrideCancelRequest,
    GovernanceOverrideCreate,
    GovernanceOverrideCreateFromTemplate,
    GovernanceOverrideDecisionRequest,
    GovernanceOverrideDetail,
    GovernanceOverrideEligibleApproverRead,
    GovernanceOverrideEventRead,
    GovernanceOverrideExpireResponse,
    GovernanceOverrideListResponse,
    GovernanceOverrideApprovalRead,
    GovernanceOverrideRejectRequest,
    GovernanceOverrideRequestRead,
    GovernanceOverrideRoutingRead,
    GovernanceOverrideSummary,
)
from app.services.audit_service import AuditService
from app.services.governance_override_service import GovernanceOverrideService

router = APIRouter(prefix="/governance/overrides", tags=["governance-overrides"])


def _request_read(payload: dict) -> GovernanceOverrideRequestRead:
    return GovernanceOverrideRequestRead(
        id=payload["id"],
        organization_id=payload["organization_id"],
        override_type=payload["override_type"],
        target_entity_type=payload["target_entity_type"],
        target_entity_id=payload["target_entity_id"],
        requested_action=payload["requested_action"],
        reason=payload["reason"],
        status=payload["status"],
        requested_by_user_id=payload["requested_by_user_id"],
        template_id=payload.get("template_id"),
        template_version=payload.get("template_version"),
        required_approvals=int(payload["required_approvals"]),
        approval_count=int(payload["approval_count"]),
        rejection_count=int(payload["rejection_count"]),
        expires_at=payload.get("expires_at"),
        executed_by_user_id=payload.get("executed_by_user_id"),
        executed_at=payload.get("executed_at"),
        cancelled_by_user_id=payload.get("cancelled_by_user_id"),
        cancelled_at=payload.get("cancelled_at"),
        cancellation_reason=payload.get("cancellation_reason"),
        execution_result_json=payload.get("execution_result_json"),
        routing_context_json=payload.get("routing_context_json"),
        approver_role_names_json=payload.get("approver_role_names_json"),
        metadata_json=payload.get("metadata_json"),
        approvals_remaining=int(payload.get("approvals_remaining", 0)),
        request_age_hours=float(payload.get("request_age_hours", 0)),
        expires_in_hours=float(payload["expires_in_hours"]) if payload.get("expires_in_hours") is not None else None,
        stale_pending=bool(payload.get("stale_pending", False)),
        last_event_at=payload.get("last_event_at"),
        context_flags=[str(item) for item in payload.get("context_flags", [])],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )


def _approval_read(row: GovernanceOverrideApproval) -> GovernanceOverrideApprovalRead:
    return GovernanceOverrideApprovalRead(
        id=row.id,
        organization_id=row.organization_id,
        override_request_id=row.override_request_id,
        approver_user_id=row.approver_user_id,
        decision=row.decision,
        reason=row.reason,
        created_at=row.created_at,
    )


def _event_read(row: GovernanceOverrideEvent) -> GovernanceOverrideEventRead:
    return GovernanceOverrideEventRead(
        id=row.id,
        organization_id=row.organization_id,
        override_request_id=row.override_request_id,
        event_type=row.event_type,
        from_status=row.from_status,
        to_status=row.to_status,
        actor_user_id=row.actor_user_id,
        details_json=row.details_json,
        created_at=row.created_at,
    )


@router.post("", response_model=GovernanceOverrideRequestRead, status_code=status.HTTP_201_CREATED)
def create_override_request(
    payload: GovernanceOverrideCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:create")),
) -> GovernanceOverrideRequestRead:
    service = GovernanceOverrideService(db)
    row = service.create_request(
        organization_id=organization.id,
        override_type=payload.override_type,
        target_entity_type=payload.target_entity_type,
        target_entity_id=payload.target_entity_id,
        requested_action=payload.requested_action,
        reason=payload.reason,
        required_approvals=payload.required_approvals,
        requested_by_user_id=current_user.id,
        expires_at=payload.expires_at,
        metadata_json=payload.metadata_json,
    )
    AuditService(db).write_audit_log(
        action="governance_override.created",
        entity_type="governance_override_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "override_type": row.override_type,
            "requested_action": row.requested_action,
            "status": row.status,
            "required_approvals": row.required_approvals,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _request_read(service.override_request_payload(row=row))


@router.post("/from-template", response_model=GovernanceOverrideRequestRead, status_code=status.HTTP_201_CREATED)
def create_override_request_from_template(
    payload: GovernanceOverrideCreateFromTemplate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:create")),
) -> GovernanceOverrideRequestRead:
    service = GovernanceOverrideService(db)
    row = service.create_request_from_template(
        organization_id=organization.id,
        template_id=payload.template_id,
        target_entity_id=payload.target_entity_id,
        reason=payload.reason,
        expires_at=payload.expires_at,
        metadata_json=payload.metadata_json,
        requested_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_override.created_from_template",
        entity_type="governance_override_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "template_id": str(row.template_id) if row.template_id else None,
            "template_version": row.template_version,
            "required_approvals": row.required_approvals,
            "approver_role_names_json": row.approver_role_names_json,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _request_read(service.override_request_payload(row=row))


@router.get("", response_model=GovernanceOverrideListResponse)
def list_override_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    override_type: str | None = Query(default=None),
    target_entity_type: str | None = Query(default=None),
    requested_action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:read")),
) -> GovernanceOverrideListResponse:
    repo = GovernanceOverrideRepository(db)
    rows = repo.list_requests(
        organization_id=organization.id,
        status=status_filter,
        override_type=override_type,
        target_entity_type=target_entity_type,
        requested_action=requested_action,
        limit=limit,
        offset=offset,
    )
    payloads = GovernanceOverrideService(db).override_request_payloads(rows=rows)
    return GovernanceOverrideListResponse(requests=[_request_read(item) for item in payloads])


@router.post("/expire", response_model=GovernanceOverrideExpireResponse)
def expire_overrides(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:execute")),
) -> GovernanceOverrideExpireResponse:
    expired_count = GovernanceOverrideService(db).expire_pending(organization_id=organization.id, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="governance_override.expired_batch",
        entity_type="governance_override_request",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"expired_count": expired_count},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return GovernanceOverrideExpireResponse(expired_count=expired_count)


@router.get("/summary", response_model=GovernanceOverrideSummary)
def override_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:read")),
) -> GovernanceOverrideSummary:
    return GovernanceOverrideSummary(**GovernanceOverrideService(db).summary(organization_id=organization.id))


@router.get("/{override_id}", response_model=GovernanceOverrideDetail)
def get_override_detail(
    override_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:read")),
) -> GovernanceOverrideDetail:
    service = GovernanceOverrideService(db)
    row = service.require_request(organization_id=organization.id, override_id=override_id)
    approvals = GovernanceOverrideRepository(db).list_approvals(organization_id=organization.id, override_request_id=row.id)
    events = GovernanceOverrideRepository(db).list_events(organization_id=organization.id, override_request_id=row.id)
    eligible_approvers = service.eligible_approvers(row=row)
    return GovernanceOverrideDetail(
        request=_request_read(service.override_request_payload(row=row)),
        approvals=[_approval_read(item) for item in approvals],
        events=[_event_read(item) for item in events],
        eligible_approvers=[
            GovernanceOverrideEligibleApproverRead(user_id=item["user_id"], role_name=item["role_name"])
            for item in eligible_approvers
        ],
    )


@router.get("/{override_id}/routing", response_model=GovernanceOverrideRoutingRead)
def get_override_routing(
    override_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:read")),
) -> GovernanceOverrideRoutingRead:
    row = GovernanceOverrideService(db).require_request(organization_id=organization.id, override_id=override_id)
    return GovernanceOverrideRoutingRead(
        override_id=row.id,
        template_id=row.template_id,
        template_version=row.template_version,
        required_approvals=row.required_approvals,
        approver_role_names_json=row.approver_role_names_json,
        routing_context_json=row.routing_context_json,
    )


@router.post("/{override_id}/approve", response_model=GovernanceOverrideRequestRead)
def approve_override(
    override_id: uuid.UUID,
    payload: GovernanceOverrideDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:approve")),
) -> GovernanceOverrideRequestRead:
    service = GovernanceOverrideService(db)
    row = service.require_request(organization_id=organization.id, override_id=override_id)
    row = service.approve(row=row, approver_user_id=current_user.id, reason=payload.reason)
    AuditService(db).write_audit_log(
        action="governance_override.approved",
        entity_type="governance_override_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "approval_count": row.approval_count, "required_approvals": row.required_approvals},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _request_read(service.override_request_payload(row=row))


@router.post("/{override_id}/reject", response_model=GovernanceOverrideRequestRead)
def reject_override(
    override_id: uuid.UUID,
    payload: GovernanceOverrideRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:approve")),
) -> GovernanceOverrideRequestRead:
    service = GovernanceOverrideService(db)
    row = service.require_request(organization_id=organization.id, override_id=override_id)
    row = service.reject(row=row, approver_user_id=current_user.id, reason=payload.reason)
    AuditService(db).write_audit_log(
        action="governance_override.rejected",
        entity_type="governance_override_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "rejection_count": row.rejection_count, "reason": payload.reason.strip()},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _request_read(service.override_request_payload(row=row))


@router.post("/{override_id}/cancel", response_model=GovernanceOverrideRequestRead)
def cancel_override(
    override_id: uuid.UUID,
    payload: GovernanceOverrideCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:cancel")),
) -> GovernanceOverrideRequestRead:
    service = GovernanceOverrideService(db)
    row = service.require_request(organization_id=organization.id, override_id=override_id)
    row = service.cancel(row=row, actor_user_id=current_user.id, reason=payload.reason)
    AuditService(db).write_audit_log(
        action="governance_override.cancelled",
        entity_type="governance_override_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "reason": row.cancellation_reason},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _request_read(service.override_request_payload(row=row))


@router.post("/{override_id}/execute", response_model=GovernanceOverrideRequestRead)
def execute_override(
    override_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override:execute")),
) -> GovernanceOverrideRequestRead:
    service = GovernanceOverrideService(db)
    row = service.require_request(organization_id=organization.id, override_id=override_id)
    try:
        row = service.execute(row=row, actor_user_id=current_user.id)
        AuditService(db).write_audit_log(
            action="governance_override.executed",
            entity_type="governance_override_request",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"status": row.status, "execution_result_json": row.execution_result_json},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        row = service.require_request(organization_id=organization.id, override_id=override_id)
        AuditService(db).write_audit_log(
            action="governance_override.execution_failed",
            entity_type="governance_override_request",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"status": row.status, "error_message": str(exc)},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        raise
    db.refresh(row)
    return _request_read(service.override_request_payload(row=row))
