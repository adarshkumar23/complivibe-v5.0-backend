import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_reviews import (
    AIReviewApproveRequest,
    AIReviewCompleteConditionalRequest,
    AIReviewConditionalRequest,
    AIReviewCreateRequest,
    AIReviewRead,
    AIReviewRejectRequest,
    AIReviewRespondRequest,
    AIReviewWithCriteriaRead,
)
from app.ai_governance.services.ai_review_service import AIReviewService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/reviews", tags=["ai-governance-reviews"])


def _review_read(row) -> AIReviewRead:
    return AIReviewRead.model_validate(row)


@router.post("", response_model=AIReviewRead, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: AIReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIReviewRead:
    row = AIReviewService(db).create_review(
        organization.id,
        payload.system_id,
        payload.review_type,
        payload,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.get("", response_model=list[AIReviewRead])
def list_reviews(
    system_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    review_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIReviewRead]:
    rows = AIReviewService(db).list_reviews(
        organization.id,
        system_id=system_id,
        status_value=status_value,
        review_type=review_type,
    )
    return [_review_read(row) for row in rows]


@router.get("/system/{system_id}", response_model=list[AIReviewRead])
def list_reviews_for_system(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIReviewRead]:
    rows = AIReviewService(db).list_reviews(organization.id, system_id=system_id)
    return [_review_read(row) for row in rows]


@router.get("/{review_id}", response_model=AIReviewWithCriteriaRead)
def get_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIReviewWithCriteriaRead:
    review, criteria = AIReviewService(db).get_review(organization.id, review_id)
    return AIReviewWithCriteriaRead(
        review=_review_read(review),
        criteria=[
            {
                "criterion_key": row.criterion_key,
                "question": row.question,
                "response": row.response,
                "notes": row.notes,
            }
            for row in criteria
        ],
    )


@router.post("/{review_id}/respond", response_model=AIReviewRead)
def respond_to_criteria(
    review_id: uuid.UUID,
    payload: AIReviewRespondRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIReviewRead:
    row = AIReviewService(db).respond_to_criteria(
        organization.id,
        review_id,
        [item.model_dump() for item in payload.responses],
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.post("/{review_id}/approve", response_model=AIReviewRead)
def approve_review(
    review_id: uuid.UUID,
    payload: AIReviewApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:approve")),
) -> AIReviewRead:
    row = AIReviewService(db).approve_review(organization.id, review_id, current_user.id, payload.decision_notes)
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.post("/{review_id}/reject", response_model=AIReviewRead)
def reject_review(
    review_id: uuid.UUID,
    payload: AIReviewRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:approve")),
) -> AIReviewRead:
    row = AIReviewService(db).reject_review(organization.id, review_id, current_user.id, payload.decision_notes)
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.post("/{review_id}/approve-with-conditions", response_model=AIReviewRead)
def approve_with_conditions(
    review_id: uuid.UUID,
    payload: AIReviewConditionalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:approve")),
) -> AIReviewRead:
    row = AIReviewService(db).approve_with_conditions(
        organization.id,
        review_id,
        current_user.id,
        payload.conditions,
        payload.decision_notes,
    )
    db.commit()
    db.refresh(row)
    return _review_read(row)


@router.post("/{review_id}/complete-conditional", response_model=AIReviewRead)
def complete_conditional(
    review_id: uuid.UUID,
    payload: AIReviewCompleteConditionalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:approve")),
) -> AIReviewRead:
    row = AIReviewService(db).complete_conditional(organization.id, review_id, current_user.id, payload.notes)
    db.commit()
    db.refresh(row)
    return _review_read(row)
