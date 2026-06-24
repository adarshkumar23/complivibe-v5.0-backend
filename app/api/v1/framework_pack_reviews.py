import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.repositories.framework_pack_review_repository import FrameworkPackReviewRepository
from app.schemas.framework_review import (
    FrameworkPackPromotionCreateRequest,
    FrameworkPackPromotionGateResult,
    FrameworkPackPromotionRejectRequest,
    FrameworkPackPromotionRequestRead,
    FrameworkPackPromotionPreflightRequest,
    FrameworkPackReviewAssignmentCancelRequest,
    FrameworkPackReviewAssignmentCompleteRequest,
    FrameworkPackReviewAssignmentCreateRequest,
    FrameworkPackReviewAssignmentRead,
    FrameworkPackReviewCompleteRequest,
    FrameworkPackReviewDetail,
    FrameworkPackReviewRunRead,
    FrameworkPackReviewSignoffCreateRequest,
    FrameworkPackReviewSignoffRead,
    FrameworkPackReviewStartRequest,
    FrameworkReviewEscalationEventRead,
    FrameworkReviewEscalationResolveRequest,
    FrameworkReviewQueueItem,
    FrameworkReviewQueueSummaryRead,
    FrameworkReviewSLAEvaluateRequest,
    FrameworkReviewSLAEvaluateResponse,
    FrameworkReviewSLAPolicyCreateRequest,
    FrameworkReviewSLAPolicyRead,
    FrameworkReviewSLAPolicyUpdateRequest,
    FrameworkReviewSummaryRead,
)
from app.services.audit_service import AuditService
from app.services.framework_pack_review_service import FrameworkPackReviewService, REVIEW_CAVEAT
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/frameworks", tags=["framework-pack-reviews"])
queue_router = APIRouter(tags=["framework-pack-reviews"])


def _require_framework_read_or_review(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if RBACService.user_has_permission(db, user_id, organization_id, "framework_content:review"):
        return
    if RBACService.user_has_permission(db, user_id, organization_id, "frameworks:read"):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: framework_content:review or frameworks:read")


def _review_read(row) -> FrameworkPackReviewRunRead:
    return FrameworkPackReviewRunRead(
        id=row.id,
        organization_id=row.organization_id,
        framework_id=row.framework_id,
        framework_version_id=row.framework_version_id,
        pack_key=row.pack_key,
        coverage_report_id=row.coverage_report_id,
        review_type=row.review_type,
        target_coverage_level=row.target_coverage_level,
        status=row.status,
        started_by_user_id=row.started_by_user_id,
        started_at=row.started_at,
        completed_by_user_id=row.completed_by_user_id,
        completed_at=row.completed_at,
        outcome=row.outcome,
        checklist_json=row.checklist_json or {},
        findings_json=row.findings_json,
        coverage_snapshot_json=row.coverage_snapshot_json or {},
        caveat=row.caveat or REVIEW_CAVEAT,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _signoff_read(row) -> FrameworkPackReviewSignoffRead:
    return FrameworkPackReviewSignoffRead(
        id=row.id,
        organization_id=row.organization_id,
        review_run_id=row.review_run_id,
        signer_user_id=row.signer_user_id,
        signer_role_name=row.signer_role_name,
        decision=row.decision,
        comment=row.comment,
        signed_at=row.signed_at,
        signoff_checksum_sha256=row.signoff_checksum_sha256,
        signoff_signature=row.signoff_signature,
        signing_key_id=row.signing_key_id,
        signature_algorithm=row.signature_algorithm,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _promotion_read(row) -> FrameworkPackPromotionRequestRead:
    return FrameworkPackPromotionRequestRead(
        id=row.id,
        organization_id=row.organization_id,
        framework_id=row.framework_id,
        framework_version_id=row.framework_version_id,
        review_run_id=row.review_run_id,
        from_coverage_level=row.from_coverage_level,
        to_coverage_level=row.to_coverage_level,
        status=row.status,
        requested_by_user_id=row.requested_by_user_id,
        requested_at=row.requested_at,
        approved_by_user_id=row.approved_by_user_id,
        approved_at=row.approved_at,
        rejected_by_user_id=row.rejected_by_user_id,
        rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        executed_by_user_id=row.executed_by_user_id,
        executed_at=row.executed_at,
        execution_result_json=row.execution_result_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=REVIEW_CAVEAT,
    )


def _assignment_read(row) -> FrameworkPackReviewAssignmentRead:
    return FrameworkPackReviewAssignmentRead(
        id=row.id,
        organization_id=row.organization_id,
        review_run_id=row.review_run_id,
        assigned_to_user_id=row.assigned_to_user_id,
        assigned_by_user_id=row.assigned_by_user_id,
        status=row.status,
        due_at=row.due_at,
        accepted_at=row.accepted_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _sla_policy_read(row) -> FrameworkReviewSLAPolicyRead:
    return FrameworkReviewSLAPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        review_type=row.review_type,
        target_coverage_level=row.target_coverage_level,
        due_days=row.due_days,
        escalation_after_days=row.escalation_after_days,
        reminder_before_days=row.reminder_before_days,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _escalation_read(row) -> FrameworkReviewEscalationEventRead:
    return FrameworkReviewEscalationEventRead(
        id=row.id,
        organization_id=row.organization_id,
        review_run_id=row.review_run_id,
        assignment_id=row.assignment_id,
        event_type=row.event_type,
        status=row.status,
        triggered_at=row.triggered_at,
        resolved_at=row.resolved_at,
        details_json=row.details_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/{framework_id}/pack-reviews", response_model=FrameworkPackReviewRunRead, status_code=status.HTTP_201_CREATED)
def start_framework_pack_review(
    framework_id: uuid.UUID,
    payload: FrameworkPackReviewStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkPackReviewRunRead:
    service = FrameworkPackReviewService(db)
    row = service.start_review(
        organization_id=organization.id,
        framework_id=framework_id,
        framework_version_id=payload.framework_version_id,
        pack_key=payload.pack_key,
        coverage_report_id=payload.coverage_report_id,
        review_type=payload.review_type,
        target_coverage_level=payload.target_coverage_level,
        checklist_json=payload.checklist_json,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_pack_review.started",
        entity_type="framework_pack_review_run",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "framework_id": str(framework_id),
            "review_type": row.review_type,
            "target_coverage_level": row.target_coverage_level,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.get("/{framework_id}/pack-reviews", response_model=list[FrameworkPackReviewRunRead])
def list_framework_pack_reviews(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[FrameworkPackReviewRunRead]:
    _require_framework_read_or_review(db, current_user.id, organization.id)
    FrameworkPackReviewService(db).require_framework(framework_id)
    rows = FrameworkPackReviewRepository(db).list_reviews(organization_id=organization.id, framework_id=framework_id)
    return [_review_read(row) for row in rows]


@router.get("/{framework_id}/pack-reviews/{review_id}", response_model=FrameworkPackReviewDetail)
def get_framework_pack_review(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkPackReviewDetail:
    _require_framework_read_or_review(db, current_user.id, organization.id)
    service = FrameworkPackReviewService(db)
    row = service.require_review(organization_id=organization.id, framework_id=framework_id, review_id=review_id)
    signoffs = FrameworkPackReviewRepository(db).list_signoffs(organization_id=organization.id, review_run_id=row.id)
    return FrameworkPackReviewDetail(
        review=_review_read(row),
        signoffs=[_signoff_read(item) for item in signoffs],
        caveat=REVIEW_CAVEAT,
    )


@router.post("/{framework_id}/pack-reviews/{review_id}/complete", response_model=FrameworkPackReviewRunRead)
def complete_framework_pack_review(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: FrameworkPackReviewCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkPackReviewRunRead:
    service = FrameworkPackReviewService(db)
    row = service.require_review(organization_id=organization.id, framework_id=framework_id, review_id=review_id)
    before = {"status": row.status, "outcome": row.outcome}
    row = service.complete_review(
        row=row,
        outcome=payload.outcome,
        checklist_json=payload.checklist_json,
        findings_json=payload.findings_json,
        caveat=payload.caveat,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_pack_review.completed",
        entity_type="framework_pack_review_run",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "outcome": row.outcome},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.post("/{framework_id}/pack-reviews/{review_id}/signoffs", response_model=FrameworkPackReviewSignoffRead, status_code=status.HTTP_201_CREATED)
def signoff_framework_pack_review(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: FrameworkPackReviewSignoffCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkPackReviewSignoffRead:
    service = FrameworkPackReviewService(db)
    row = service.require_review(organization_id=organization.id, framework_id=framework_id, review_id=review_id)
    signoff = service.create_signoff(
        row=row,
        signer_user_id=current_user.id,
        decision=payload.decision,
        comment=payload.comment,
    )
    AuditService(db).write_audit_log(
        action="framework_pack_review.signoff_created",
        entity_type="framework_pack_review_signoff",
        entity_id=signoff.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "review_run_id": str(row.id),
            "decision": signoff.decision,
            "signer_role_name": signoff.signer_role_name,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(signoff)
    return _signoff_read(signoff)


@router.post("/{framework_id}/pack-promotions/preflight", response_model=FrameworkPackPromotionGateResult)
def preflight_framework_pack_promotion(
    framework_id: uuid.UUID,
    payload: FrameworkPackPromotionPreflightRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkPackPromotionGateResult:
    _ = current_user
    gate = FrameworkPackReviewService(db).evaluate_promotion_gates(
        organization_id=organization.id,
        framework_id=framework_id,
        review_run_id=payload.review_run_id,
        to_coverage_level=payload.to_coverage_level,
    )
    return FrameworkPackPromotionGateResult(**gate)


@router.post("/{framework_id}/pack-promotions", response_model=FrameworkPackPromotionRequestRead, status_code=status.HTTP_201_CREATED)
def create_framework_pack_promotion_request(
    framework_id: uuid.UUID,
    payload: FrameworkPackPromotionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:promote")),
) -> FrameworkPackPromotionRequestRead:
    service = FrameworkPackReviewService(db)
    row = service.create_promotion_request(
        organization_id=organization.id,
        framework_id=framework_id,
        review_run_id=payload.review_run_id,
        to_coverage_level=payload.to_coverage_level,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_pack_promotion.requested",
        entity_type="framework_pack_promotion_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "review_run_id": str(row.review_run_id),
            "from_coverage_level": row.from_coverage_level,
            "to_coverage_level": row.to_coverage_level,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _promotion_read(row)


@router.post("/{framework_id}/pack-promotions/{promotion_id}/approve", response_model=FrameworkPackPromotionRequestRead)
def approve_framework_pack_promotion(
    framework_id: uuid.UUID,
    promotion_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:promote")),
) -> FrameworkPackPromotionRequestRead:
    service = FrameworkPackReviewService(db)
    row = service.require_promotion(organization_id=organization.id, framework_id=framework_id, promotion_id=promotion_id)
    before = {"status": row.status}
    row = service.approve_promotion(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="framework_pack_promotion.approved",
        entity_type="framework_pack_promotion_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _promotion_read(row)


@router.post("/{framework_id}/pack-promotions/{promotion_id}/reject", response_model=FrameworkPackPromotionRequestRead)
def reject_framework_pack_promotion(
    framework_id: uuid.UUID,
    promotion_id: uuid.UUID,
    payload: FrameworkPackPromotionRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:promote")),
) -> FrameworkPackPromotionRequestRead:
    service = FrameworkPackReviewService(db)
    row = service.require_promotion(organization_id=organization.id, framework_id=framework_id, promotion_id=promotion_id)
    before = {"status": row.status}
    row = service.reject_promotion(row=row, actor_user_id=current_user.id, rejection_reason=payload.rejection_reason)
    AuditService(db).write_audit_log(
        action="framework_pack_promotion.rejected",
        entity_type="framework_pack_promotion_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "rejection_reason": row.rejection_reason},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _promotion_read(row)


@router.post("/{framework_id}/pack-promotions/{promotion_id}/execute", response_model=FrameworkPackPromotionRequestRead)
def execute_framework_pack_promotion(
    framework_id: uuid.UUID,
    promotion_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:promote")),
) -> FrameworkPackPromotionRequestRead:
    service = FrameworkPackReviewService(db)
    row = service.require_promotion(organization_id=organization.id, framework_id=framework_id, promotion_id=promotion_id)
    before = {"status": row.status}
    row = service.execute_promotion(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="framework_pack_promotion.executed",
        entity_type="framework_pack_promotion_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "from_coverage_level": row.from_coverage_level,
            "to_coverage_level": row.to_coverage_level,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _promotion_read(row)


@router.get("/{framework_id}/pack-promotions", response_model=list[FrameworkPackPromotionRequestRead])
def list_framework_pack_promotions(
    framework_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[FrameworkPackPromotionRequestRead]:
    _ = limit
    _require_framework_read_or_review(db, current_user.id, organization.id)
    FrameworkPackReviewService(db).require_framework(framework_id)
    rows = FrameworkPackReviewRepository(db).list_promotions(organization_id=organization.id, framework_id=framework_id)
    return [_promotion_read(row) for row in rows]


@router.get("/{framework_id}/review-summary", response_model=FrameworkReviewSummaryRead)
def framework_review_summary(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewSummaryRead:
    _require_framework_read_or_review(db, current_user.id, organization.id)
    result = FrameworkPackReviewService(db).review_summary(organization_id=organization.id, framework_id=framework_id)
    return FrameworkReviewSummaryRead(**result)


@router.post(
    "/{framework_id}/pack-reviews/{review_id}/assignments",
    response_model=FrameworkPackReviewAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_framework_review(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: FrameworkPackReviewAssignmentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkPackReviewAssignmentRead:
    service = FrameworkPackReviewService(db)
    assignment, queued_email_id = service.create_assignment(
        organization_id=organization.id,
        framework_id=framework_id,
        review_id=review_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        assigned_by_user_id=current_user.id,
        due_at=payload.due_at,
        notes=payload.notes,
        notify=payload.notify,
    )
    AuditService(db).write_audit_log(
        action="framework_pack_review.assignment_created",
        entity_type="framework_pack_review_assignment",
        entity_id=assignment.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "review_run_id": str(assignment.review_run_id),
            "assigned_to_user_id": str(assignment.assigned_to_user_id),
            "status": assignment.status,
            "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
            "queued_email_id": str(queued_email_id) if queued_email_id else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_read(assignment)


@router.get("/{framework_id}/pack-reviews/{review_id}/assignments", response_model=list[FrameworkPackReviewAssignmentRead])
def list_framework_review_assignments(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkPackReviewAssignmentRead]:
    rows = FrameworkPackReviewService(db).list_assignments_for_review(
        organization_id=organization.id,
        framework_id=framework_id,
        review_id=review_id,
    )
    return [_assignment_read(row) for row in rows]


@queue_router.get("/framework-review-queue/my", response_model=list[FrameworkReviewQueueItem])
def my_framework_review_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[FrameworkReviewQueueItem]:
    now = datetime.now(UTC)
    service = FrameworkPackReviewService(db)
    rows = service.list_assignments_for_user(organization_id=organization.id, user_id=current_user.id)
    items: list[FrameworkReviewQueueItem] = []
    for row in rows:
        if status_filter and row.status != status_filter:
            continue
        due_at = row.due_at.replace(tzinfo=UTC) if row.due_at is not None and row.due_at.tzinfo is None else row.due_at
        is_overdue = row.status == "overdue" or (row.status in {"assigned", "accepted"} and due_at is not None and due_at < now)
        if overdue_only and not is_overdue:
            continue
        review = FrameworkPackReviewRepository(db).get_review(row.review_run_id)
        if review is None or review.organization_id != organization.id:
            continue
        items.append(
            FrameworkReviewQueueItem(
                assignment=_assignment_read(row),
                review_type=review.review_type,
                target_coverage_level=review.target_coverage_level,
                framework_id=review.framework_id,
                is_overdue=is_overdue,
            )
        )
    return items


@queue_router.get("/framework-review-queue", response_model=list[FrameworkReviewQueueItem])
def organization_framework_review_queue(
    assigned_to_user_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    review_type: str | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkReviewQueueItem]:
    now = datetime.now(UTC)
    service = FrameworkPackReviewService(db)
    rows = service.list_assignments_for_org(organization_id=organization.id)
    items: list[FrameworkReviewQueueItem] = []
    for row in rows:
        if assigned_to_user_id and row.assigned_to_user_id != assigned_to_user_id:
            continue
        if status_filter and row.status != status_filter:
            continue
        due_at = row.due_at.replace(tzinfo=UTC) if row.due_at is not None and row.due_at.tzinfo is None else row.due_at
        is_overdue = row.status == "overdue" or (row.status in {"assigned", "accepted"} and due_at is not None and due_at < now)
        if overdue_only and not is_overdue:
            continue
        review = FrameworkPackReviewRepository(db).get_review(row.review_run_id)
        if review is None or review.organization_id != organization.id:
            continue
        if review_type and review.review_type != review_type:
            continue
        items.append(
            FrameworkReviewQueueItem(
                assignment=_assignment_read(row),
                review_type=review.review_type,
                target_coverage_level=review.target_coverage_level,
                framework_id=review.framework_id,
                is_overdue=is_overdue,
            )
        )
    return items


@queue_router.post("/framework-review-assignments/{assignment_id}/accept", response_model=FrameworkPackReviewAssignmentRead)
def accept_framework_review_assignment(
    assignment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkPackReviewAssignmentRead:
    service = FrameworkPackReviewService(db)
    row = service.require_assignment(organization_id=organization.id, assignment_id=assignment_id)
    before = {"status": row.status}
    row = service.accept_assignment(assignment=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="framework_pack_review.assignment_accepted",
        entity_type="framework_pack_review_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assignment_read(row)


@queue_router.post("/framework-review-assignments/{assignment_id}/complete", response_model=FrameworkPackReviewAssignmentRead)
def complete_framework_review_assignment(
    assignment_id: uuid.UUID,
    payload: FrameworkPackReviewAssignmentCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkPackReviewAssignmentRead:
    service = FrameworkPackReviewService(db)
    row = service.require_assignment(organization_id=organization.id, assignment_id=assignment_id)
    before = {"status": row.status}
    row = service.complete_assignment(assignment=row, actor_user_id=current_user.id, notes=payload.notes)
    AuditService(db).write_audit_log(
        action="framework_pack_review.assignment_completed",
        entity_type="framework_pack_review_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "completed_at": row.completed_at.isoformat() if row.completed_at else None},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assignment_read(row)


@queue_router.post("/framework-review-assignments/{assignment_id}/cancel", response_model=FrameworkPackReviewAssignmentRead)
def cancel_framework_review_assignment(
    assignment_id: uuid.UUID,
    payload: FrameworkPackReviewAssignmentCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkPackReviewAssignmentRead:
    service = FrameworkPackReviewService(db)
    row = service.require_assignment(organization_id=organization.id, assignment_id=assignment_id)
    before = {"status": row.status}
    row = service.cancel_assignment(assignment=row, reason=payload.reason)
    AuditService(db).write_audit_log(
        action="framework_pack_review.assignment_cancelled",
        entity_type="framework_pack_review_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "notes": row.notes},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _assignment_read(row)


@queue_router.post("/framework-review-sla-policies", response_model=FrameworkReviewSLAPolicyRead, status_code=status.HTTP_201_CREATED)
def create_framework_review_sla_policy(
    payload: FrameworkReviewSLAPolicyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewSLAPolicyRead:
    row = FrameworkPackReviewService(db).create_sla_policy(
        organization_id=organization.id,
        name=payload.name,
        review_type=payload.review_type,
        target_coverage_level=payload.target_coverage_level,
        due_days=payload.due_days,
        escalation_after_days=payload.escalation_after_days,
        reminder_before_days=payload.reminder_before_days,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_review_sla_policy.created",
        entity_type="framework_review_sla_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"review_type": row.review_type, "target_coverage_level": row.target_coverage_level, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sla_policy_read(row)


@queue_router.get("/framework-review-sla-policies", response_model=list[FrameworkReviewSLAPolicyRead])
def list_framework_review_sla_policies(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkReviewSLAPolicyRead]:
    rows = FrameworkPackReviewService(db).list_sla_policies(organization_id=organization.id)
    return [_sla_policy_read(row) for row in rows]


@queue_router.patch("/framework-review-sla-policies/{policy_id}", response_model=FrameworkReviewSLAPolicyRead)
def update_framework_review_sla_policy(
    policy_id: uuid.UUID,
    payload: FrameworkReviewSLAPolicyUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewSLAPolicyRead:
    service = FrameworkPackReviewService(db)
    row = service.require_sla_policy(organization_id=organization.id, policy_id=policy_id)
    before = {"name": row.name, "status": row.status}
    row = service.update_sla_policy(
        row=row,
        name=payload.name,
        review_type=payload.review_type,
        target_coverage_level=payload.target_coverage_level,
        due_days=payload.due_days,
        escalation_after_days=payload.escalation_after_days,
        reminder_before_days=payload.reminder_before_days,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="framework_review_sla_policy.updated",
        entity_type="framework_review_sla_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"name": row.name, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sla_policy_read(row)


@queue_router.post("/framework-review-sla-policies/{policy_id}/archive", response_model=FrameworkReviewSLAPolicyRead)
def archive_framework_review_sla_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewSLAPolicyRead:
    service = FrameworkPackReviewService(db)
    row = service.require_sla_policy(organization_id=organization.id, policy_id=policy_id)
    before = {"status": row.status}
    row = service.archive_sla_policy(row=row)
    AuditService(db).write_audit_log(
        action="framework_review_sla_policy.archived",
        entity_type="framework_review_sla_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sla_policy_read(row)


@queue_router.post("/framework-review-queue/evaluate-sla", response_model=FrameworkReviewSLAEvaluateResponse)
def evaluate_framework_review_sla(
    payload: FrameworkReviewSLAEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewSLAEvaluateResponse:
    result = FrameworkPackReviewService(db).evaluate_sla(
        organization_id=organization.id,
        dry_run=payload.dry_run,
        notify=payload.notify,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_review_sla.evaluated",
        entity_type="framework_review_sla",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json=result,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return FrameworkReviewSLAEvaluateResponse(**result)


@queue_router.get("/framework-review-escalations", response_model=list[FrameworkReviewEscalationEventRead])
def list_framework_review_escalations(
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = Query(default=None),
    review_run_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkReviewEscalationEventRead]:
    rows = FrameworkPackReviewService(db).list_escalation_events(organization_id=organization.id)
    filtered = []
    for row in rows:
        if status_filter and row.status != status_filter:
            continue
        if event_type and row.event_type != event_type:
            continue
        if review_run_id and row.review_run_id != review_run_id:
            continue
        filtered.append(row)
    return [_escalation_read(row) for row in filtered]


@queue_router.post("/framework-review-escalations/{event_id}/resolve", response_model=FrameworkReviewEscalationEventRead)
def resolve_framework_review_escalation(
    event_id: uuid.UUID,
    payload: FrameworkReviewEscalationResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewEscalationEventRead:
    service = FrameworkPackReviewService(db)
    row = service.require_escalation_event(organization_id=organization.id, event_id=event_id)
    before = {"status": row.status}
    row = service.resolve_escalation_event(row=row, resolution_notes=payload.resolution_notes)
    AuditService(db).write_audit_log(
        action="framework_review_escalation.resolved",
        entity_type="framework_review_escalation_event",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _escalation_read(row)


@queue_router.get("/framework-review-queue/summary", response_model=FrameworkReviewQueueSummaryRead)
def framework_review_queue_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewQueueSummaryRead:
    summary = FrameworkPackReviewService(db).review_queue_summary(organization_id=organization.id)
    return FrameworkReviewQueueSummaryRead(**summary)
