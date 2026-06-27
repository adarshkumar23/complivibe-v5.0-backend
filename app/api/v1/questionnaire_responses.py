import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.questionnaire_scoring_service import QuestionnaireScoringService
from app.compliance.services.questionnaire_template_service import QuestionnaireTemplateService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.user import User
from app.models.vendor_questionnaire_answer import VendorQuestionnaireAnswer
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.schemas.questionnaire import (
    ScoreBreakdownRead,
    VendorQuestionnaireAnswerRead,
    VendorQuestionnaireAnswerSubmit,
    VendorQuestionnaireBulkAnswerSubmit,
    VendorQuestionnaireBulkSubmitResult,
    VendorQuestionnaireResponseCreate,
    VendorQuestionnaireResponseDetailRead,
    VendorQuestionnaireResponseRead,
    VendorQuestionnaireRiskAggregate,
    VendorQuestionnaireTransitionRequest,
)
from app.services.seed_service import SeedService

router = APIRouter(prefix="/compliance/questionnaire-responses", tags=["questionnaire-responses"])


def _response_read(row: VendorQuestionnaireResponse) -> VendorQuestionnaireResponseRead:
    return VendorQuestionnaireResponseRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        template_id=row.template_id,
        title=row.title,
        status=row.status,
        sent_at=row.sent_at,
        due_date=row.due_date,
        responded_at=row.responded_at,
        completed_at=row.completed_at,
        calculated_risk_score=row.calculated_risk_score,
        score_computed_at=row.score_computed_at,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _answer_read(row: VendorQuestionnaireAnswer, question: QuestionnaireTemplateQuestion | None = None) -> VendorQuestionnaireAnswerRead:
    return VendorQuestionnaireAnswerRead(
        id=row.id,
        organization_id=row.organization_id,
        response_id=row.response_id,
        question_id=row.question_id,
        answer_text=row.answer_text,
        answer_value=row.answer_value,
        score_contribution=row.score_contribution,
        is_answered=row.is_answered,
        created_at=row.created_at,
        updated_at=row.updated_at,
        question_text=question.question_text if question else None,
        category_tag=question.category_tag if question else None,
    )


@router.post("", response_model=VendorQuestionnaireResponseRead, status_code=status.HTTP_201_CREATED)
def create_questionnaire_response(
    payload: VendorQuestionnaireResponseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorQuestionnaireResponseRead:
    SeedService.ensure_questionnaire_scoring_rules(db)
    row = QuestionnaireTemplateService(db).create_response(
        organization.id,
        payload.vendor_id,
        payload.template_id,
        payload,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _response_read(row)


@router.get("", response_model=list[VendorQuestionnaireResponseRead])
def list_questionnaire_responses(
    vendor_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    template_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[VendorQuestionnaireResponseRead]:
    rows = QuestionnaireTemplateService(db).list_responses(
        organization.id,
        vendor_id=vendor_id,
        status_value=status_value,
        template_id=template_id,
    )
    return [_response_read(row) for row in rows]


@router.get("/{response_id}", response_model=VendorQuestionnaireResponseDetailRead)
def get_questionnaire_response(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> VendorQuestionnaireResponseDetailRead:
    response, rows = QuestionnaireTemplateService(db).get_response_with_answers(organization.id, response_id)
    return VendorQuestionnaireResponseDetailRead(
        **_response_read(response).model_dump(),
        answers=[_answer_read(answer, question) for answer, question in rows],
    )


@router.post("/{response_id}/answers", response_model=VendorQuestionnaireAnswerRead)
def submit_questionnaire_answer(
    response_id: uuid.UUID,
    payload: VendorQuestionnaireAnswerSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorQuestionnaireAnswerRead:
    SeedService.ensure_questionnaire_scoring_rules(db)
    answer = QuestionnaireTemplateService(db).submit_answer(
        organization.id,
        response_id,
        payload.question_id,
        payload.answer_text,
        payload.answer_value,
        current_user.id,
    )
    db.commit()
    db.refresh(answer)
    return _answer_read(answer)


@router.post("/{response_id}/answers/bulk", response_model=VendorQuestionnaireBulkSubmitResult)
def bulk_submit_questionnaire_answers(
    response_id: uuid.UUID,
    payload: VendorQuestionnaireBulkAnswerSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorQuestionnaireBulkSubmitResult:
    SeedService.ensure_questionnaire_scoring_rules(db)
    result = QuestionnaireTemplateService(db).bulk_submit_answers(
        organization.id,
        response_id,
        payload.answers,
        current_user.id,
    )
    db.commit()
    return VendorQuestionnaireBulkSubmitResult(**result)


@router.post("/{response_id}/transition", response_model=VendorQuestionnaireResponseRead)
def transition_questionnaire_response(
    response_id: uuid.UUID,
    payload: VendorQuestionnaireTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorQuestionnaireResponseRead:
    row = QuestionnaireTemplateService(db).transition_response_status(
        organization.id,
        response_id,
        payload.new_status,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _response_read(row)


@router.get("/{response_id}/score", response_model=ScoreBreakdownRead)
def questionnaire_score_breakdown(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> ScoreBreakdownRead:
    payload = QuestionnaireScoringService(db).get_score_breakdown(organization.id, response_id)
    return ScoreBreakdownRead(**payload)


@router.get("/vendor/{vendor_id}/risk", response_model=VendorQuestionnaireRiskAggregate)
def vendor_questionnaire_risk(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> VendorQuestionnaireRiskAggregate:
    payload = QuestionnaireScoringService(db).get_vendor_risk_score_from_questionnaires(organization.id, vendor_id)
    return VendorQuestionnaireRiskAggregate(**payload)
