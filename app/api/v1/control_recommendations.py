import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.obligation_control_recommendation import ObligationControlRecommendation
from app.models.organization import Organization
from app.models.recommendation_generation_run import RecommendationGenerationRun
from app.models.user import User
from app.schemas.control_recommendation import (
    ControlRecommendationApplyRequest,
    ControlRecommendationDismissRequest,
    ControlRecommendationGenerateRequest,
    ControlRecommendationGenerateResponse,
    ControlRecommendationRead,
    ControlRecommendationSummary,
    RecommendationGenerationRunRead,
)
from app.services.audit_service import AuditService
from app.services.control_recommendation_service import CONTROL_RECOMMENDATION_CAVEAT, ControlRecommendationService
from app.services.rbac_service import RBACService

router = APIRouter(tags=["control_recommendations"])


def _recommendation_read(row: ObligationControlRecommendation | dict) -> ControlRecommendationRead:
    if isinstance(row, dict):
        data = {
            "id": row.get("id") or uuid.uuid4(),
            "organization_id": row["organization_id"],
            "framework_id": row["framework_id"],
            "obligation_id": row["obligation_id"],
            "suggestion_id": row.get("suggestion_id"),
            "recommendation_type": row["recommendation_type"],
            "priority": row["priority"],
            "status": row["status"],
            "title": row["title"],
            "rationale": row["rationale"],
            "recommended_control_title": row.get("recommended_control_title"),
            "recommended_control_description": row.get("recommended_control_description"),
            "existing_control_id": row.get("existing_control_id"),
            "created_control_id": row.get("created_control_id"),
            "confidence_level": row["confidence_level"],
            "source": row["source"],
            "provenance_json": row.get("provenance_json"),
            "generated_by_user_id": row.get("generated_by_user_id"),
            "generated_at": row["generated_at"],
            "applied_by_user_id": row.get("applied_by_user_id"),
            "applied_at": row.get("applied_at"),
            "dismissed_by_user_id": row.get("dismissed_by_user_id"),
            "dismissed_at": row.get("dismissed_at"),
            "dismissal_reason": row.get("dismissal_reason"),
            "metadata_json": row.get("metadata_json"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    else:
        data = {
            "id": row.id,
            "organization_id": row.organization_id,
            "framework_id": row.framework_id,
            "obligation_id": row.obligation_id,
            "suggestion_id": row.suggestion_id,
            "recommendation_type": row.recommendation_type,
            "priority": row.priority,
            "status": row.status,
            "title": row.title,
            "rationale": row.rationale,
            "recommended_control_title": row.recommended_control_title,
            "recommended_control_description": row.recommended_control_description,
            "existing_control_id": row.existing_control_id,
            "created_control_id": row.created_control_id,
            "confidence_level": row.confidence_level,
            "source": row.source,
            "provenance_json": row.provenance_json,
            "generated_by_user_id": row.generated_by_user_id,
            "generated_at": row.generated_at,
            "applied_by_user_id": row.applied_by_user_id,
            "applied_at": row.applied_at,
            "dismissed_by_user_id": row.dismissed_by_user_id,
            "dismissed_at": row.dismissed_at,
            "dismissal_reason": row.dismissal_reason,
            "metadata_json": row.metadata_json,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    return ControlRecommendationRead(**data)


def _run_read(row: RecommendationGenerationRun) -> RecommendationGenerationRunRead:
    return RecommendationGenerationRunRead(
        id=row.id,
        organization_id=row.organization_id,
        framework_id=row.framework_id,
        dry_run=row.dry_run,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        evaluated_obligations_count=row.evaluated_obligations_count,
        recommendations_created_count=row.recommendations_created_count,
        recommendations_skipped_duplicate_count=row.recommendations_skipped_duplicate_count,
        recommendations_would_create_count=row.recommendations_would_create_count,
        summary_json=row.summary_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post(
    "/frameworks/{framework_id}/control-recommendations/generate",
    response_model=ControlRecommendationGenerateResponse,
)
def generate_control_recommendations(
    framework_id: uuid.UUID,
    payload: ControlRecommendationGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlRecommendationGenerateResponse:
    if not RBACService.user_has_permission(db, current_user.id, organization.id, "frameworks:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: frameworks:read")
    if not payload.dry_run and not RBACService.user_has_permission(db, current_user.id, organization.id, "controls:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: controls:write")

    service = ControlRecommendationService(db)
    run_row, rows, summary = service.generate_for_framework(
        organization_id=organization.id,
        framework_id=framework_id,
        actor_user_id=current_user.id,
        dry_run=payload.dry_run,
        include_non_applicable_review=payload.include_non_applicable_review,
        limit=payload.limit,
    )

    AuditService(db).write_audit_log(
        action="control_recommendations.generated",
        entity_type="recommendation_generation_run",
        entity_id=run_row.id if run_row else None,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "framework_id": str(framework_id),
            "dry_run": payload.dry_run,
            "summary": summary,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if payload.dry_run:
        db.rollback()
    else:
        db.commit()

    return ControlRecommendationGenerateResponse(
        run_id=run_row.id if run_row else None,
        dry_run=payload.dry_run,
        recommendations=[_recommendation_read(row) for row in rows],
        summary=summary,
        caveat=CONTROL_RECOMMENDATION_CAVEAT,
    )


@router.get("/control-recommendations", response_model=list[ControlRecommendationRead])
def list_control_recommendations(
    framework_id: uuid.UUID | None = Query(default=None),
    obligation_id: uuid.UUID | None = Query(default=None),
    recommendation_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[ControlRecommendationRead]:
    rows = ControlRecommendationService(db).repo.list_recommendations(
        organization_id=organization.id,
        framework_id=framework_id,
        obligation_id=obligation_id,
        recommendation_type=recommendation_type,
        priority=priority,
        status=status,
        source=source,
        limit=limit,
        offset=offset,
    )
    return [_recommendation_read(row) for row in rows]


@router.get("/control-recommendations/runs", response_model=list[RecommendationGenerationRunRead])
def list_recommendation_generation_runs(
    framework_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[RecommendationGenerationRunRead]:
    rows = ControlRecommendationService(db).repo.list_runs(
        organization_id=organization.id,
        framework_id=framework_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_run_read(row) for row in rows]


@router.get("/control-recommendations/summary", response_model=ControlRecommendationSummary)
def control_recommendation_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlRecommendationSummary:
    summary = ControlRecommendationService(db).repo.summary(organization.id)
    return ControlRecommendationSummary(**summary)


@router.get("/control-recommendations/{recommendation_id}", response_model=ControlRecommendationRead)
def get_control_recommendation_detail(
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlRecommendationRead:
    row = ControlRecommendationService(db).repo.get_recommendation(recommendation_id)
    if row is None or row.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    return _recommendation_read(row)


@router.post("/control-recommendations/{recommendation_id}/apply", response_model=ControlRecommendationRead)
def apply_control_recommendation(
    recommendation_id: uuid.UUID,
    payload: ControlRecommendationApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlRecommendationRead:
    row = ControlRecommendationService(db).apply_recommendation(
        organization_id=organization.id,
        recommendation_id=recommendation_id,
        actor_user_id=current_user.id,
        existing_control_id=payload.existing_control_id,
        create_control=payload.create_control,
        notes=payload.notes,
    )

    AuditService(db).write_audit_log(
        action="control_recommendation.applied",
        entity_type="obligation_control_recommendation",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "recommendation_type": row.recommendation_type,
            "obligation_id": str(row.obligation_id),
            "created_control_id": str(row.created_control_id) if row.created_control_id else None,
            "existing_control_id": str(row.existing_control_id) if row.existing_control_id else None,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _recommendation_read(row)


@router.post("/control-recommendations/{recommendation_id}/dismiss", response_model=ControlRecommendationRead)
def dismiss_control_recommendation(
    recommendation_id: uuid.UUID,
    payload: ControlRecommendationDismissRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlRecommendationRead:
    row = ControlRecommendationService(db).dismiss_recommendation(
        organization_id=organization.id,
        recommendation_id=recommendation_id,
        actor_user_id=current_user.id,
        dismissal_reason=payload.dismissal_reason,
    )

    AuditService(db).write_audit_log(
        action="control_recommendation.dismissed",
        entity_type="obligation_control_recommendation",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "dismissal_reason": row.dismissal_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _recommendation_read(row)
