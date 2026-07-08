from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.bcm import BiaAssessment, BusinessProcess
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.bcm import (
    BiaAssessmentCreateRequest,
    BiaAssessmentHistoryResponse,
    BiaAssessmentRead,
    BusinessProcessCreateRequest,
    BusinessProcessRead,
    BusinessProcessUpdateRequest,
    OverdueReviewItem,
    OverdueReviewsResponse,
)
from app.services.audit_service import AuditService
from app.services.bcm_service import BcmService

router = APIRouter(prefix="/bcm", tags=["bcm"])


def _process_read(process: BusinessProcess) -> BusinessProcessRead:
    return BusinessProcessRead.model_validate(process)


def _bia_read(bia: BiaAssessment) -> BiaAssessmentRead:
    return BiaAssessmentRead.model_validate(bia)


def _request_meta(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.post("/processes", response_model=BusinessProcessRead, status_code=201)
def create_process(
    payload: BusinessProcessCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:manage")),
) -> BusinessProcessRead:
    service = BcmService(db)
    process = service.create_process(
        organization.id,
        data=payload.model_dump(),
        created_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="business_process.created",
        entity_type="business_process",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=process.id,
        after_json=payload.model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(process)
    return _process_read(process)


@router.get("/processes", response_model=list[BusinessProcessRead])
def list_processes(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:read")),
) -> list[BusinessProcessRead]:
    service = BcmService(db)
    return [_process_read(process) for process in service.list_processes(organization.id)]


@router.get("/processes/{process_id}", response_model=BusinessProcessRead)
def get_process(
    process_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:read")),
) -> BusinessProcessRead:
    service = BcmService(db)
    process = service.get_process(organization.id, process_id)
    return _process_read(process)


@router.patch("/processes/{process_id}", response_model=BusinessProcessRead)
def update_process(
    process_id: uuid.UUID,
    payload: BusinessProcessUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:manage")),
) -> BusinessProcessRead:
    service = BcmService(db)
    before = service.get_process(organization.id, process_id)
    before_snapshot = _process_read(before).model_dump(mode="json")
    data = payload.model_dump(exclude_unset=True)
    process = service.update_process(organization.id, process_id, data=data)
    AuditService(db).write_audit_log(
        action="business_process.updated",
        entity_type="business_process",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=process.id,
        before_json=before_snapshot,
        after_json=_process_read(process).model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(process)
    return _process_read(process)


@router.post("/processes/{process_id}/bia", response_model=BiaAssessmentRead, status_code=201)
def create_bia_assessment(
    process_id: uuid.UUID,
    payload: BiaAssessmentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:manage")),
) -> BiaAssessmentRead:
    service = BcmService(db)
    bia = service.create_bia_assessment(organization.id, process_id, data=payload.model_dump())
    AuditService(db).write_audit_log(
        action="bia_assessment.created",
        entity_type="bia_assessment",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=bia.id,
        after_json=payload.model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(bia)
    return _bia_read(bia)


@router.get("/processes/{process_id}/bia", response_model=BiaAssessmentHistoryResponse)
def get_bia_assessment(
    process_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:read")),
) -> BiaAssessmentHistoryResponse:
    service = BcmService(db)
    process = service.get_process(organization.id, process_id)
    history = service.list_bia_history(organization.id, process_id)
    latest = history[0] if history else None
    context = service.build_bia_context(organization.id, process, latest)
    return BiaAssessmentHistoryResponse(
        latest=_bia_read(latest) if latest else None,
        history=[_bia_read(item) for item in history],
        is_stale=context["is_stale"],
        context_flags=context["context_flags"],
    )


@router.get("/overdue-reviews", response_model=OverdueReviewsResponse)
def get_overdue_reviews(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("bcm:read")),
) -> OverdueReviewsResponse:
    service = BcmService(db)
    items = service.list_overdue_reviews(organization.id)
    return OverdueReviewsResponse(
        items=[
            OverdueReviewItem(
                process_id=item["process_id"],
                process_name=item["process_name"],
                criticality_tier=item["criticality_tier"],
                latest_bia=_bia_read(item["latest_bia"]) if item["latest_bia"] else None,
                is_stale=item["is_stale"],
                stale_reasons=item["stale_reasons"],
            )
            for item in items
        ]
    )
