import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.schemas.framework_review_capacity import (
    FrameworkReviewBatchAssignmentApplyRequest,
    FrameworkReviewBatchAssignmentApplyResponse,
    FrameworkReviewBatchAssignmentCancelRequest,
    FrameworkReviewBatchAssignmentCancellationRequestCreateRequest,
    FrameworkReviewBatchAssignmentCancellationRequestRejectRequest,
    FrameworkReviewBatchAssignmentCancellationRequirementUpdateRequest,
    FrameworkReviewBatchCancellationRequestRead,
    FrameworkReviewBatchAssignmentRunDetailRead,
    FrameworkReviewBatchAssignmentRunItemRead,
    FrameworkReviewBatchAssignmentRunRead,
    FrameworkReviewBatchAssignmentSummaryRead,
    FrameworkReviewBatchAssignmentValidateRequest,
    FrameworkReviewBatchAssignmentValidationResponse,
    FrameworkReviewAssignmentSuggestionApplyRequest,
    FrameworkReviewAssignmentSuggestionDismissRequest,
    FrameworkReviewAssignmentSuggestionGenerateRequest,
    FrameworkReviewAssignmentSuggestionGenerateResponse,
    FrameworkReviewAssignmentSuggestionGeneratedItem,
    FrameworkReviewAssignmentSuggestionRead,
    FrameworkReviewAssignmentSuggestionSimulateRequest,
    FrameworkReviewAssignmentSuggestionSimulateResponse,
    FrameworkReviewCapacitySummaryRead,
    FrameworkReviewCapacitySimulationSummaryRead,
    FrameworkReviewWaveSimulationRequest,
    FrameworkReviewWaveSimulationResponse,
    FrameworkReviewerCapacityPolicyCreateRequest,
    FrameworkReviewerCapacityPolicyRead,
    FrameworkReviewerCapacitySimulationPolicyRequest,
    FrameworkReviewerCapacitySimulationResponse,
    FrameworkReviewerCapacityPolicyUpdateRequest,
    FrameworkReviewerWorkloadCalculateRequest,
    FrameworkReviewerWorkloadCalculateResponse,
    FrameworkReviewerWorkloadSnapshotRead,
)
from app.services.audit_service import AuditService
from app.services.framework_review_capacity_service import FrameworkReviewCapacityService
from app.services.rbac_service import RBACService

router = APIRouter(tags=["framework-review-capacity"])


def _policy_read(row) -> FrameworkReviewerCapacityPolicyRead:
    return FrameworkReviewerCapacityPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        role_name=row.role_name,
        max_active_assignments=row.max_active_assignments,
        max_overdue_assignments=row.max_overdue_assignments,
        preferred_review_types_json=row.preferred_review_types_json,
        preferred_target_coverage_levels_json=row.preferred_target_coverage_levels_json,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _workload_read(row, *, role_name: str | None = None) -> FrameworkReviewerWorkloadSnapshotRead:
    snapshot_json = row.snapshot_json or {}
    role = role_name or snapshot_json.get("role_name") or "unknown"
    return FrameworkReviewerWorkloadSnapshotRead(
        id=getattr(row, "id", None),
        organization_id=row.organization_id,
        user_id=row.user_id,
        role_name=role,
        active_assignments=row.active_assignments,
        accepted_assignments=row.accepted_assignments,
        overdue_assignments=row.overdue_assignments,
        completed_assignments_last_30d=row.completed_assignments_last_30d,
        open_escalations=row.open_escalations,
        workload_score=row.workload_score,
        capacity_remaining=row.capacity_remaining,
        snapshot_json=snapshot_json,
        calculated_at=row.calculated_at,
        created_at=getattr(row, "created_at", None),
    )


def _suggestion_read(row) -> FrameworkReviewAssignmentSuggestionRead:
    return FrameworkReviewAssignmentSuggestionRead(
        id=row.id,
        organization_id=row.organization_id,
        review_run_id=row.review_run_id,
        suggested_user_id=row.suggested_user_id,
        score=row.score,
        rank=row.rank,
        status=row.status,
        rationale=row.rationale,
        scoring_json=row.scoring_json or {},
        generated_by_user_id=row.generated_by_user_id,
        generated_at=row.generated_at,
        applied_by_user_id=row.applied_by_user_id,
        applied_at=row.applied_at,
        created_assignment_id=row.created_assignment_id,
        dismissed_by_user_id=row.dismissed_by_user_id,
        dismissed_at=row.dismissed_at,
        dismissal_reason=row.dismissal_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _batch_item_read(row) -> FrameworkReviewBatchAssignmentRunItemRead:
    return FrameworkReviewBatchAssignmentRunItemRead(
        id=row.id,
        organization_id=row.organization_id,
        batch_run_id=row.batch_run_id,
        review_run_id=row.review_run_id,
        assigned_to_user_id=row.assigned_to_user_id,
        status=row.status,
        created_assignment_id=row.created_assignment_id,
        skipped_reason=row.skipped_reason,
        error_message=row.error_message,
        scoring_json=row.scoring_json,
        rationale=row.rationale,
        created_at=row.created_at,
    )


def _batch_run_read(row) -> FrameworkReviewBatchAssignmentRunRead:
    return FrameworkReviewBatchAssignmentRunRead(
        id=row.id,
        organization_id=row.organization_id,
        status=row.status,
        plan_hash=row.plan_hash,
        confirmation_text=row.confirmation_text,
        requested_by_user_id=row.requested_by_user_id,
        applied_by_user_id=row.applied_by_user_id,
        applied_at=row.applied_at,
        cancelled_by_user_id=row.cancelled_by_user_id,
        cancelled_at=row.cancelled_at,
        cancellation_reason=row.cancellation_reason,
        cancellation_metadata_json=row.cancellation_metadata_json,
        cancellation_requires_approval=row.cancellation_requires_approval,
        cancellation_request_id=row.cancellation_request_id,
        total_items=row.total_items,
        created_assignments_count=row.created_assignments_count,
        skipped_items_count=row.skipped_items_count,
        failed_items_count=row.failed_items_count,
        notify_assignees=row.notify_assignees,
        validation_report_json=row.validation_report_json or {},
        result_json=row.result_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _batch_cancellation_request_read(row) -> FrameworkReviewBatchCancellationRequestRead:
    return FrameworkReviewBatchCancellationRequestRead(
        id=row.id,
        organization_id=row.organization_id,
        batch_run_id=row.batch_run_id,
        status=row.status,
        reason=row.reason,
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
    )


def _has_any_permission(db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID, permission_codes: list[str]) -> bool:
    for code in permission_codes:
        if RBACService.user_has_permission(db, user_id, organization_id, code):
            return True
    return False


def _require_capacity_read_or_review(db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if _has_any_permission(
        db,
        user_id=user_id,
        organization_id=organization_id,
        permission_codes=["framework_review_capacity:read", "framework_content:review"],
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Missing required permission: framework_review_capacity:read or framework_content:review",
    )


def _require_capacity_write_or_review(db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if _has_any_permission(
        db,
        user_id=user_id,
        organization_id=organization_id,
        permission_codes=["framework_review_capacity:write", "framework_content:review"],
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Missing required permission: framework_review_capacity:write or framework_content:review",
    )


@router.post(
    "/framework-review-capacity/policies",
    response_model=FrameworkReviewerCapacityPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_capacity_policy(
    payload: FrameworkReviewerCapacityPolicyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewerCapacityPolicyRead:
    _require_capacity_write_or_review(db, user_id=current_user.id, organization_id=organization.id)
    service = FrameworkReviewCapacityService(db)
    row = service.create_capacity_policy(
        organization_id=organization.id,
        name=payload.name,
        role_name=payload.role_name,
        max_active_assignments=payload.max_active_assignments,
        max_overdue_assignments=payload.max_overdue_assignments,
        preferred_review_types_json=payload.preferred_review_types_json,
        preferred_target_coverage_levels_json=payload.preferred_target_coverage_levels_json,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_reviewer_capacity_policy.created",
        entity_type="framework_reviewer_capacity_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "role_name": row.role_name,
            "status": row.status,
            "max_active_assignments": row.max_active_assignments,
            "max_overdue_assignments": row.max_overdue_assignments,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/framework-review-capacity/policies", response_model=list[FrameworkReviewerCapacityPolicyRead])
def list_capacity_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[FrameworkReviewerCapacityPolicyRead]:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    rows = FrameworkReviewCapacityService(db).list_capacity_policies(organization_id=organization.id)
    return [_policy_read(row) for row in rows]


@router.patch("/framework-review-capacity/policies/{policy_id}", response_model=FrameworkReviewerCapacityPolicyRead)
def update_capacity_policy(
    policy_id: uuid.UUID,
    payload: FrameworkReviewerCapacityPolicyUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewerCapacityPolicyRead:
    _require_capacity_write_or_review(db, user_id=current_user.id, organization_id=organization.id)
    service = FrameworkReviewCapacityService(db)
    row = service.require_capacity_policy(organization_id=organization.id, policy_id=policy_id)
    before = {
        "name": row.name,
        "role_name": row.role_name,
        "status": row.status,
        "max_active_assignments": row.max_active_assignments,
        "max_overdue_assignments": row.max_overdue_assignments,
    }
    row = service.update_capacity_policy(
        row=row,
        name=payload.name,
        role_name=payload.role_name,
        max_active_assignments=payload.max_active_assignments,
        max_overdue_assignments=payload.max_overdue_assignments,
        preferred_review_types_json=payload.preferred_review_types_json,
        preferred_target_coverage_levels_json=payload.preferred_target_coverage_levels_json,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="framework_reviewer_capacity_policy.updated",
        entity_type="framework_reviewer_capacity_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "role_name": row.role_name,
            "status": row.status,
            "max_active_assignments": row.max_active_assignments,
            "max_overdue_assignments": row.max_overdue_assignments,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/framework-review-capacity/policies/{policy_id}/archive", response_model=FrameworkReviewerCapacityPolicyRead)
def archive_capacity_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewerCapacityPolicyRead:
    _require_capacity_write_or_review(db, user_id=current_user.id, organization_id=organization.id)
    service = FrameworkReviewCapacityService(db)
    row = service.require_capacity_policy(organization_id=organization.id, policy_id=policy_id)
    before = {"status": row.status}
    row = service.archive_capacity_policy(row=row)
    AuditService(db).write_audit_log(
        action="framework_reviewer_capacity_policy.archived",
        entity_type="framework_reviewer_capacity_policy",
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
    return _policy_read(row)


@router.post("/framework-review-capacity/workload/calculate", response_model=FrameworkReviewerWorkloadCalculateResponse)
def calculate_workload(
    payload: FrameworkReviewerWorkloadCalculateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewerWorkloadCalculateResponse:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    service = FrameworkReviewCapacityService(db)
    rows = service.calculate_workload(organization_id=organization.id, persist=payload.persist)

    if payload.persist:
        AuditService(db).write_audit_log(
            action="framework_reviewer_workload.calculated",
            entity_type="framework_reviewer_workload_snapshot",
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"persist": True, "count": len(rows)},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()

    return FrameworkReviewerWorkloadCalculateResponse(
        persist=payload.persist,
        count=len(rows),
        snapshots=[_workload_read(row) for row in rows],
    )


@router.get("/framework-review-capacity/workload", response_model=list[FrameworkReviewerWorkloadSnapshotRead])
def list_workload(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[FrameworkReviewerWorkloadSnapshotRead]:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    rows = FrameworkReviewCapacityService(db).list_workload(organization_id=organization.id)
    return [_workload_read(row) for row in rows]


@router.post(
    "/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/generate",
    response_model=FrameworkReviewAssignmentSuggestionGenerateResponse,
)
def generate_assignment_suggestions(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: FrameworkReviewAssignmentSuggestionGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewAssignmentSuggestionGenerateResponse:
    service = FrameworkReviewCapacityService(db)
    review, persisted_rows, ranked = service.generate_assignment_suggestions(
        organization_id=organization.id,
        framework_id=framework_id,
        review_id=review_id,
        persist=payload.persist,
        limit=payload.limit,
        actor_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="framework_review_assignment_suggestions.generated",
        entity_type="framework_review_assignment_suggestion",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "framework_id": str(framework_id),
            "review_run_id": str(review.id),
            "persist": payload.persist,
            "count": len(persisted_rows) if payload.persist else len(ranked),
            "limit": payload.limit,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    suggestions: list[FrameworkReviewAssignmentSuggestionGeneratedItem] = []
    if payload.persist:
        for row in persisted_rows:
            suggestions.append(
                FrameworkReviewAssignmentSuggestionGeneratedItem(
                    id=row.id,
                    organization_id=row.organization_id,
                    review_run_id=row.review_run_id,
                    suggested_user_id=row.suggested_user_id,
                    score=row.score,
                    rank=row.rank,
                    status=row.status,
                    rationale=row.rationale,
                    scoring_json=row.scoring_json or {},
                    generated_by_user_id=row.generated_by_user_id,
                    generated_at=row.generated_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
    else:
        for entry in ranked:
            suggestions.append(
                FrameworkReviewAssignmentSuggestionGeneratedItem(
                    id=None,
                    organization_id=entry["organization_id"],
                    review_run_id=entry["review_run_id"],
                    suggested_user_id=entry["suggested_user_id"],
                    score=entry["score"],
                    rank=entry["rank"],
                    status=entry["status"],
                    rationale=entry["rationale"],
                    scoring_json=entry["scoring_json"],
                    generated_by_user_id=entry["generated_by_user_id"],
                    generated_at=entry["generated_at"],
                    created_at=None,
                    updated_at=None,
                )
            )

    return FrameworkReviewAssignmentSuggestionGenerateResponse(
        persist=payload.persist,
        limit=payload.limit,
        count=len(suggestions),
        suggestions=suggestions,
    )


@router.get(
    "/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions",
    response_model=list[FrameworkReviewAssignmentSuggestionRead],
)
def list_assignment_suggestions(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkReviewAssignmentSuggestionRead]:
    rows = FrameworkReviewCapacityService(db).list_assignment_suggestions(
        organization_id=organization.id,
        framework_id=framework_id,
        review_id=review_id,
    )
    return [_suggestion_read(row) for row in rows]


@router.post(
    "/framework-review-assignment-suggestions/{suggestion_id}/apply",
    response_model=FrameworkReviewAssignmentSuggestionRead,
)
def apply_assignment_suggestion(
    suggestion_id: uuid.UUID,
    payload: FrameworkReviewAssignmentSuggestionApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewAssignmentSuggestionRead:
    service = FrameworkReviewCapacityService(db)
    suggestion, assignment = service.apply_assignment_suggestion(
        organization_id=organization.id,
        suggestion_id=suggestion_id,
        actor_user_id=current_user.id,
        due_at=payload.due_at,
        notes=payload.notes,
    )
    AuditService(db).write_audit_log(
        action="framework_review_assignment_suggestion.applied",
        entity_type="framework_review_assignment_suggestion",
        entity_id=suggestion.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": suggestion.status,
            "created_assignment_id": str(assignment.id),
            "review_run_id": str(suggestion.review_run_id),
            "suggested_user_id": str(suggestion.suggested_user_id),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(suggestion)
    return _suggestion_read(suggestion)


@router.post(
    "/framework-review-assignment-suggestions/{suggestion_id}/dismiss",
    response_model=FrameworkReviewAssignmentSuggestionRead,
)
def dismiss_assignment_suggestion(
    suggestion_id: uuid.UUID,
    payload: FrameworkReviewAssignmentSuggestionDismissRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewAssignmentSuggestionRead:
    service = FrameworkReviewCapacityService(db)
    suggestion = service.dismiss_assignment_suggestion(
        organization_id=organization.id,
        suggestion_id=suggestion_id,
        actor_user_id=current_user.id,
        dismissal_reason=payload.dismissal_reason,
    )
    AuditService(db).write_audit_log(
        action="framework_review_assignment_suggestion.dismissed",
        entity_type="framework_review_assignment_suggestion",
        entity_id=suggestion.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": suggestion.status,
            "dismissal_reason": suggestion.dismissal_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(suggestion)
    return _suggestion_read(suggestion)


@router.get("/framework-review-capacity/summary", response_model=FrameworkReviewCapacitySummaryRead)
def capacity_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewCapacitySummaryRead:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    summary = FrameworkReviewCapacityService(db).capacity_summary(organization_id=organization.id)
    return FrameworkReviewCapacitySummaryRead(**summary)


@router.post(
    "/framework-review-capacity/simulations/policy",
    response_model=FrameworkReviewerCapacitySimulationResponse,
)
def simulate_capacity_policy(
    payload: FrameworkReviewerCapacitySimulationPolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewerCapacitySimulationResponse:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    service = FrameworkReviewCapacityService(db)
    simulation = service.simulate_capacity_policy(
        organization_id=organization.id,
        role_name=payload.role_name,
        max_active_assignments=payload.max_active_assignments,
        max_overdue_assignments=payload.max_overdue_assignments,
        preferred_review_types_json=payload.preferred_review_types_json,
        preferred_target_coverage_levels_json=payload.preferred_target_coverage_levels_json,
        review_type=payload.review_type,
        target_coverage_level=payload.target_coverage_level,
    )
    AuditService(db).write_audit_log(
        action="framework_reviewer_capacity.simulation_run",
        entity_type="framework_reviewer_capacity_policy",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "role_name": payload.role_name,
            "max_active_assignments": payload.max_active_assignments,
            "max_overdue_assignments": payload.max_overdue_assignments,
            "review_type": payload.review_type,
            "target_coverage_level": payload.target_coverage_level,
            "reviewer_count": len(simulation["reviewer_comparisons"]),
        },
        metadata_json={"source": "api", "provenance": simulation["provenance"]},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return FrameworkReviewerCapacitySimulationResponse(**simulation)


@router.post(
    "/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/simulate",
    response_model=FrameworkReviewAssignmentSuggestionSimulateResponse,
)
def simulate_assignment_suggestions(
    framework_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: FrameworkReviewAssignmentSuggestionSimulateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewAssignmentSuggestionSimulateResponse:
    service = FrameworkReviewCapacityService(db)
    proposed_payload = payload.proposed_policy_json.model_dump() if payload.proposed_policy_json is not None else None
    review, ranked, proposed_policy_used = service.simulate_assignment_suggestions(
        organization_id=organization.id,
        framework_id=framework_id,
        review_id=review_id,
        limit=payload.limit,
        actor_user_id=current_user.id,
        proposed_policy_json=proposed_payload,
    )
    AuditService(db).write_audit_log(
        action="framework_review_assignment_suggestions.simulated",
        entity_type="framework_review_assignment_suggestion",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "framework_id": str(framework_id),
            "review_run_id": str(review.id),
            "limit": payload.limit,
            "count": len(ranked),
            "proposed_policy_supplied": payload.proposed_policy_json is not None,
        },
        metadata_json={"source": "api", "provenance": "deterministic_policy_simulation_v1"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    suggestions = [
        FrameworkReviewAssignmentSuggestionGeneratedItem(
            id=None,
            organization_id=entry["organization_id"],
            review_run_id=entry["review_run_id"],
            suggested_user_id=entry["suggested_user_id"],
            score=entry["score"],
            rank=entry["rank"],
            status=entry["status"],
            rationale=entry["rationale"],
            scoring_json=entry["scoring_json"],
            generated_by_user_id=entry["generated_by_user_id"],
            generated_at=entry["generated_at"],
            created_at=None,
            updated_at=None,
        )
        for entry in ranked
    ]

    return FrameworkReviewAssignmentSuggestionSimulateResponse(
        review_id=review.id,
        proposed_policy_used=proposed_policy_used,
        simulated_suggestions=suggestions,
        scoring_formula=service.scoring_formula(),
        provenance="deterministic_policy_simulation_v1",
        caveat=(
            "This simulation is deterministic and preview-only. "
            "It does not create assignments, persist suggestions, or change reviewer workload."
        ),
    )


@router.get(
    "/framework-review-capacity/simulations/summary",
    response_model=FrameworkReviewCapacitySimulationSummaryRead,
)
def simulation_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewCapacitySimulationSummaryRead:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    summary = FrameworkReviewCapacityService(db).simulation_summary(organization_id=organization.id)
    return FrameworkReviewCapacitySimulationSummaryRead(**summary)


@router.post(
    "/framework-review-capacity/simulations/review-waves",
    response_model=FrameworkReviewWaveSimulationResponse,
)
def simulate_review_waves(
    payload: FrameworkReviewWaveSimulationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> FrameworkReviewWaveSimulationResponse:
    _require_capacity_read_or_review(db, user_id=current_user.id, organization_id=organization.id)
    service = FrameworkReviewCapacityService(db)
    proposed_payload = payload.proposed_policy_json.model_dump() if payload.proposed_policy_json is not None else None
    simulation = service.simulate_review_waves(
        organization_id=organization.id,
        framework_id=payload.framework_id,
        review_ids=payload.review_ids,
        review_type=payload.review_type,
        target_coverage_level=payload.target_coverage_level,
        max_waves=payload.max_waves,
        max_reviews_per_wave=payload.max_reviews_per_wave,
        proposed_policy_json=proposed_payload,
        limit_reviewers=payload.limit_reviewers,
        include_existing_assignments=payload.include_existing_assignments,
    )
    AuditService(db).write_audit_log(
        action="framework_review_capacity.wave_simulation_run",
        entity_type="framework_pack_review_run",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "simulation_id": simulation["simulation_id"],
            "selected_reviews_count": simulation["selected_reviews_count"],
            "waves": len(simulation["waves"]),
            "unassigned_reviews": len(simulation["unassigned_reviews"]),
            "max_waves": payload.max_waves,
            "max_reviews_per_wave": payload.max_reviews_per_wave,
            "review_ids_supplied": len(payload.review_ids or []),
            "limit_reviewers_supplied": len(payload.limit_reviewers or []),
            "include_existing_assignments": payload.include_existing_assignments,
        },
        metadata_json={"source": "api", "provenance": simulation["provenance"]},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return FrameworkReviewWaveSimulationResponse(**simulation)


@router.post(
    "/framework-review-capacity/batch-assignments/validate",
    response_model=FrameworkReviewBatchAssignmentValidationResponse,
)
def validate_batch_assignments(
    payload: FrameworkReviewBatchAssignmentValidateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchAssignmentValidationResponse:
    service = FrameworkReviewCapacityService(db)
    validation = service.validate_batch_assignment_plan(
        organization_id=organization.id,
        assignments=[item.model_dump() for item in payload.assignments] if payload.assignments is not None else None,
        wave_simulation_payload=payload.wave_simulation_payload.model_dump()
        if payload.wave_simulation_payload is not None
        else None,
        notify_assignees=payload.notify_assignees,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_assignment.validated",
        entity_type="framework_review_batch_assignment_run",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "plan_hash": validation["plan_hash"],
            "total_items": validation["total_items"],
            "valid_items": validation["valid_items"],
            "invalid_items": validation["invalid_items"],
            "notify_assignees": payload.notify_assignees,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return FrameworkReviewBatchAssignmentValidationResponse(**validation)


@router.post(
    "/framework-review-capacity/batch-assignments/apply",
    response_model=FrameworkReviewBatchAssignmentApplyResponse,
)
def apply_batch_assignments(
    payload: FrameworkReviewBatchAssignmentApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchAssignmentApplyResponse:
    service = FrameworkReviewCapacityService(db)
    run, _, result = service.apply_batch_assignment_plan(
        organization_id=organization.id,
        requested_by_user_id=current_user.id,
        applied_by_user_id=current_user.id,
        provided_plan_hash=payload.plan_hash,
        confirmation_text=payload.confirmation_text,
        assignments=[item.model_dump() for item in payload.assignments] if payload.assignments is not None else None,
        wave_simulation_payload=payload.wave_simulation_payload.model_dump()
        if payload.wave_simulation_payload is not None
        else None,
        notify_assignees=payload.notify_assignees,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_assignment.applied",
        entity_type="framework_review_batch_assignment_run",
        entity_id=run.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": run.status,
            "plan_hash": run.plan_hash,
            "total_items": run.total_items,
            "created_assignments_count": run.created_assignments_count,
            "skipped_items_count": run.skipped_items_count,
            "failed_items_count": run.failed_items_count,
            "notify_assignees": run.notify_assignees,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(run)
    return FrameworkReviewBatchAssignmentApplyResponse(**result)


@router.get(
    "/framework-review-capacity/batch-assignments/runs",
    response_model=list[FrameworkReviewBatchAssignmentRunRead],
)
def list_batch_assignment_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkReviewBatchAssignmentRunRead]:
    rows = FrameworkReviewCapacityService(db).list_batch_assignment_runs(
        organization_id=organization.id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return [_batch_run_read(row) for row in rows]


@router.get(
    "/framework-review-capacity/batch-assignments/runs/{run_id}",
    response_model=FrameworkReviewBatchAssignmentRunDetailRead,
)
def get_batch_assignment_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchAssignmentRunDetailRead:
    service = FrameworkReviewCapacityService(db)
    run = service.get_batch_assignment_run(organization_id=organization.id, run_id=run_id)
    items = service.list_batch_assignment_items(organization_id=organization.id, run_id=run_id)
    return FrameworkReviewBatchAssignmentRunDetailRead(
        **_batch_run_read(run).model_dump(),
        items=[_batch_item_read(row) for row in items],
    )


@router.post(
    "/framework-review-capacity/batch-assignments/runs/{run_id}/cancel",
    response_model=FrameworkReviewBatchAssignmentRunRead,
)
def cancel_batch_assignment_run(
    run_id: uuid.UUID,
    payload: FrameworkReviewBatchAssignmentCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchAssignmentRunRead:
    service = FrameworkReviewCapacityService(db)
    run = service.cancel_batch_assignment_run(
        organization_id=organization.id,
        run_id=run_id,
        cancelled_by_user_id=current_user.id,
        cancellation_reason=payload.cancellation_reason,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_assignment.cancelled",
        entity_type="framework_review_batch_assignment_run",
        entity_id=run.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": run.status,
            "cancellation_reason": run.cancellation_reason,
            "cancelled_at": run.cancelled_at.isoformat() if run.cancelled_at else None,
            "created_assignments_count": run.created_assignments_count,
        },
        metadata_json={"source": "api", "cancellation_metadata_json": run.cancellation_metadata_json},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(run)
    return _batch_run_read(run)


@router.post(
    "/framework-review-capacity/batch-assignments/runs/{run_id}/require-cancellation-approval",
    response_model=FrameworkReviewBatchAssignmentRunRead,
)
def update_batch_cancellation_requirement(
    run_id: uuid.UUID,
    payload: FrameworkReviewBatchAssignmentCancellationRequirementUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchAssignmentRunRead:
    service = FrameworkReviewCapacityService(db)
    run = service.update_batch_cancellation_requirement(
        organization_id=organization.id,
        run_id=run_id,
        enabled=payload.enabled,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_cancellation.requirement_updated",
        entity_type="framework_review_batch_assignment_run",
        entity_id=run.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "cancellation_requires_approval": run.cancellation_requires_approval,
            "status": run.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(run)
    return _batch_run_read(run)


@router.post(
    "/framework-review-capacity/batch-assignments/runs/{run_id}/cancellation-requests",
    response_model=FrameworkReviewBatchCancellationRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_batch_cancellation_request(
    run_id: uuid.UUID,
    payload: FrameworkReviewBatchAssignmentCancellationRequestCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchCancellationRequestRead:
    service = FrameworkReviewCapacityService(db)
    row = service.create_batch_cancellation_request(
        organization_id=organization.id,
        run_id=run_id,
        requested_by_user_id=current_user.id,
        reason=payload.reason,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_cancellation.requested",
        entity_type="framework_review_batch_cancellation_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "batch_run_id": str(row.batch_run_id),
            "status": row.status,
            "reason": row.reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _batch_cancellation_request_read(row)


@router.get(
    "/framework-review-capacity/batch-assignments/cancellation-requests",
    response_model=list[FrameworkReviewBatchCancellationRequestRead],
)
def list_batch_cancellation_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    batch_run_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> list[FrameworkReviewBatchCancellationRequestRead]:
    rows = FrameworkReviewCapacityService(db).list_batch_cancellation_requests(
        organization_id=organization.id,
        status_filter=status_filter,
        batch_run_id=batch_run_id,
        limit=limit,
        offset=offset,
    )
    return [_batch_cancellation_request_read(row) for row in rows]


@router.get(
    "/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}",
    response_model=FrameworkReviewBatchCancellationRequestRead,
)
def get_batch_cancellation_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchCancellationRequestRead:
    row = FrameworkReviewCapacityService(db).get_batch_cancellation_request(
        organization_id=organization.id,
        request_id=request_id,
    )
    return _batch_cancellation_request_read(row)


@router.post(
    "/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve",
    response_model=FrameworkReviewBatchCancellationRequestRead,
)
def approve_batch_cancellation_request(
    request_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchCancellationRequestRead:
    service = FrameworkReviewCapacityService(db)
    row = service.approve_batch_cancellation_request(
        organization_id=organization.id,
        request_id=request_id,
        approved_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_cancellation.approved",
        entity_type="framework_review_batch_cancellation_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "batch_run_id": str(row.batch_run_id),
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _batch_cancellation_request_read(row)


@router.post(
    "/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/reject",
    response_model=FrameworkReviewBatchCancellationRequestRead,
)
def reject_batch_cancellation_request(
    request_id: uuid.UUID,
    payload: FrameworkReviewBatchAssignmentCancellationRequestRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchCancellationRequestRead:
    service = FrameworkReviewCapacityService(db)
    row = service.reject_batch_cancellation_request(
        organization_id=organization.id,
        request_id=request_id,
        rejected_by_user_id=current_user.id,
        rejection_reason=payload.rejection_reason,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_cancellation.rejected",
        entity_type="framework_review_batch_cancellation_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "batch_run_id": str(row.batch_run_id),
            "rejection_reason": row.rejection_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _batch_cancellation_request_read(row)


@router.post(
    "/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/execute",
    response_model=FrameworkReviewBatchCancellationRequestRead,
)
def execute_batch_cancellation_request(
    request_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchCancellationRequestRead:
    service = FrameworkReviewCapacityService(db)
    row, run = service.execute_batch_cancellation_request(
        organization_id=organization.id,
        request_id=request_id,
        executed_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="framework_review_batch_cancellation.executed",
        entity_type="framework_review_batch_cancellation_request",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "batch_run_id": str(row.batch_run_id),
            "run_status": run.status,
            "cancelled_at": run.cancelled_at.isoformat() if run.cancelled_at else None,
        },
        metadata_json={"source": "api", "execution_result_json": row.execution_result_json},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _batch_cancellation_request_read(row)


@router.get(
    "/framework-review-capacity/batch-assignments/summary",
    response_model=FrameworkReviewBatchAssignmentSummaryRead,
)
def batch_assignment_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("framework_content:review")),
) -> FrameworkReviewBatchAssignmentSummaryRead:
    summary = FrameworkReviewCapacityService(db).batch_assignment_summary(organization_id=organization.id)
    return FrameworkReviewBatchAssignmentSummaryRead(**summary)
