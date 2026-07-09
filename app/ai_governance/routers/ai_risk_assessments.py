import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_risk_assessments import (
    AIRiskAssessmentQuestionRead,
    AIRiskAssessmentRead,
    AIRiskAssessmentResponseSubmitRequest,
    ComputeBiasRequest,
)
from app.ai_governance.services.ai_risk_assessment_service import AIRiskAssessmentService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

systems_router = APIRouter(prefix="/ai-governance/systems", tags=["ai-governance-risk-assessments"])
router = APIRouter(prefix="/ai-governance/risk-assessments", tags=["ai-governance-risk-assessments"])


@systems_router.post("/{system_id}/risk-assessments", response_model=AIRiskAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_ai_risk_assessment(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskAssessmentRead:
    service = AIRiskAssessmentService(db)
    row = service.create_assessment(organization.id, system_id, current_user.id)
    db.commit()
    db.refresh(row)
    return service.to_read(organization.id, row)


@systems_router.get("/{system_id}/risk-assessments", response_model=list[AIRiskAssessmentRead])
def list_ai_risk_assessments_for_system(
    system_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIRiskAssessmentRead]:
    service = AIRiskAssessmentService(db)
    rows = service.list_assessments(
        organization.id,
        system_id=system_id,
        status_filter=status_filter,
    )
    return [service.to_read(organization.id, row) for row in rows]


@router.get("/questions", response_model=list[AIRiskAssessmentQuestionRead])
def list_ai_risk_assessment_questions(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIRiskAssessmentQuestionRead]:
    """Discovery endpoint: lists the active AI risk assessment question bank
    (id, risk_dimension, question_text, weight, order_index) so callers can
    look up valid question_id values before calling submit-responses, instead
    of having to guess IDs ahead of time."""
    rows = AIRiskAssessmentService(db).list_questions()
    db.commit()
    return [AIRiskAssessmentQuestionRead.model_validate(row) for row in rows]


@router.get("/{assessment_id}", response_model=AIRiskAssessmentRead)
def get_ai_risk_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIRiskAssessmentRead:
    service = AIRiskAssessmentService(db)
    row = service.get_assessment(organization.id, assessment_id)
    return service.to_read(organization.id, row)


@router.post("/{assessment_id}/submit-responses", response_model=AIRiskAssessmentRead)
def submit_ai_risk_assessment_responses(
    assessment_id: uuid.UUID,
    payload: AIRiskAssessmentResponseSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskAssessmentRead:
    service = AIRiskAssessmentService(db)
    row = service.submit_responses(
        organization.id,
        assessment_id,
        [item.model_dump() for item in payload.responses],
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return service.to_read(organization.id, row)


@router.post("/{assessment_id}/complete", response_model=AIRiskAssessmentRead)
def complete_ai_risk_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskAssessmentRead:
    service = AIRiskAssessmentService(db)
    row = service.complete_assessment(organization.id, assessment_id, current_user.id)
    db.commit()
    db.refresh(row)
    return service.to_read(organization.id, row)


@router.post("/{assessment_id}/compute-bias")
def compute_bias_metrics(
    assessment_id: uuid.UUID,
    payload: ComputeBiasRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> dict:
    result = AIRiskAssessmentService(db).compute_bias(
        organization.id,
        assessment_id,
        payload.predictions,
        payload.protected_attribute_values,
        payload.labels,
        current_user.id,
    )
    db.commit()
    return result
