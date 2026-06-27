import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai_governance.schemas.third_party_model_card_aibom import (
    ThirdPartyAIAssessmentRead,
    ThirdPartyAIAssessmentUpdate,
)
from app.ai_governance.services.third_party_ai_service import ThirdPartyAIService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/third-party-assessments", tags=["ai-governance-third-party-ai"])


@router.get("", response_model=list[ThirdPartyAIAssessmentRead])
def list_third_party_assessments(
    vendor_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
    __: Membership = Depends(require_permission("ai_governance:read")),
) -> list[ThirdPartyAIAssessmentRead]:
    rows = ThirdPartyAIService(db).list_assessments(
        organization.id,
        vendor_id=vendor_id,
        status_filter=status_filter,
        risk_level=risk_level,
    )
    return [ThirdPartyAIAssessmentRead.model_validate(row) for row in rows]


@router.get("/{assessment_id}", response_model=ThirdPartyAIAssessmentRead)
def get_third_party_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
    __: Membership = Depends(require_permission("ai_governance:read")),
) -> ThirdPartyAIAssessmentRead:
    row = ThirdPartyAIService(db).get_assessment(organization.id, assessment_id)
    return ThirdPartyAIAssessmentRead.model_validate(row)


@router.patch("/{assessment_id}", response_model=ThirdPartyAIAssessmentRead)
def update_third_party_assessment(
    assessment_id: uuid.UUID,
    payload: ThirdPartyAIAssessmentUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
    __: Membership = Depends(require_permission("ai_governance:write")),
) -> ThirdPartyAIAssessmentRead:
    row = ThirdPartyAIService(db).update_assessment(organization.id, assessment_id, payload)
    db.commit()
    db.refresh(row)
    return ThirdPartyAIAssessmentRead.model_validate(row)


@router.post("/{assessment_id}/complete", response_model=ThirdPartyAIAssessmentRead)
def complete_third_party_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
    __: Membership = Depends(require_permission("ai_governance:write")),
) -> ThirdPartyAIAssessmentRead:
    row = ThirdPartyAIService(db).complete_assessment(organization.id, assessment_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ThirdPartyAIAssessmentRead.model_validate(row)


@router.delete("/{assessment_id}", response_model=ThirdPartyAIAssessmentRead)
def delete_third_party_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
    __: Membership = Depends(require_permission("ai_governance:write")),
) -> ThirdPartyAIAssessmentRead:
    row = ThirdPartyAIService(db).soft_delete_assessment(organization.id, assessment_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ThirdPartyAIAssessmentRead.model_validate(row)
