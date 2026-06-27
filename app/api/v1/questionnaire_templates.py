import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.questionnaire_template_service import QuestionnaireTemplateService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.questionnaire_template_section import QuestionnaireTemplateSection
from app.models.user import User
from app.schemas.questionnaire import (
    QuestionnaireTemplateCloneRequest,
    QuestionnaireTemplateCreate,
    QuestionnaireTemplateDetailRead,
    QuestionnaireTemplateQuestionCreate,
    QuestionnaireTemplateQuestionRead,
    QuestionnaireTemplateRead,
    QuestionnaireTemplateSectionCreate,
    QuestionnaireTemplateSectionRead,
)
from app.services.seed_service import SeedService

router = APIRouter(prefix="/compliance/questionnaire-templates", tags=["questionnaire-templates"])


def _template_read(row: QuestionnaireTemplate) -> QuestionnaireTemplateRead:
    return QuestionnaireTemplateRead(
        id=row.id,
        organization_id=row.organization_id,
        template_type=row.template_type,
        name=row.name,
        version=row.version,
        description=row.description,
        is_system_template=row.is_system_template,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _section_read(row: QuestionnaireTemplateSection) -> QuestionnaireTemplateSectionRead:
    return QuestionnaireTemplateSectionRead(
        id=row.id,
        template_id=row.template_id,
        title=row.title,
        description=row.description,
        order_index=row.order_index,
        created_at=row.created_at,
    )


def _question_read(row: QuestionnaireTemplateQuestion) -> QuestionnaireTemplateQuestionRead:
    return QuestionnaireTemplateQuestionRead(
        id=row.id,
        template_id=row.template_id,
        section_id=row.section_id,
        question_text=row.question_text,
        question_type=row.question_type,
        category_tag=row.category_tag,
        framework_ref=row.framework_ref,
        allowed_values=row.allowed_values,
        expected_answer=row.expected_answer,
        is_required=row.is_required,
        order_index=row.order_index,
        help_text=row.help_text,
        created_at=row.created_at,
    )


@router.get("", response_model=list[QuestionnaireTemplateRead])
def list_questionnaire_templates(
    template_type: str | None = Query(default=None),
    include_system: bool = Query(default=True),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[QuestionnaireTemplateRead]:
    SeedService.ensure_questionnaire_templates(db)
    rows = QuestionnaireTemplateService(db).list_templates(
        organization.id,
        template_type=template_type,
        include_system=include_system,
    )
    return [_template_read(row) for row in rows]


@router.post("", response_model=QuestionnaireTemplateRead, status_code=status.HTTP_201_CREATED)
def create_custom_questionnaire_template(
    payload: QuestionnaireTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireTemplateRead:
    row = QuestionnaireTemplateService(db).create_custom_template(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.get("/{template_id}", response_model=QuestionnaireTemplateDetailRead)
def get_questionnaire_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> QuestionnaireTemplateDetailRead:
    SeedService.ensure_questionnaire_templates(db)
    template, sections, questions = QuestionnaireTemplateService(db).get_template(organization.id, template_id)
    return QuestionnaireTemplateDetailRead(
        **_template_read(template).model_dump(),
        sections=[_section_read(row) for row in sections],
        questions=[_question_read(row) for row in questions],
    )


@router.post("/{template_id}/clone", response_model=QuestionnaireTemplateRead, status_code=status.HTTP_201_CREATED)
def clone_questionnaire_template(
    template_id: uuid.UUID,
    payload: QuestionnaireTemplateCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireTemplateRead:
    SeedService.ensure_questionnaire_templates(db)
    row = QuestionnaireTemplateService(db).clone_template(organization.id, template_id, payload.new_name, current_user.id)
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.delete("/{template_id}", response_model=QuestionnaireTemplateRead)
def delete_questionnaire_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireTemplateRead:
    row = QuestionnaireTemplateService(db).soft_delete_template(organization.id, template_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.post("/{template_id}/sections", response_model=QuestionnaireTemplateSectionRead, status_code=status.HTTP_201_CREATED)
def add_questionnaire_template_section(
    template_id: uuid.UUID,
    payload: QuestionnaireTemplateSectionCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireTemplateSectionRead:
    row = QuestionnaireTemplateService(db).add_section(organization.id, template_id, payload)
    db.commit()
    db.refresh(row)
    return _section_read(row)


@router.post(
    "/{template_id}/sections/{section_id}/questions",
    response_model=QuestionnaireTemplateQuestionRead,
    status_code=status.HTTP_201_CREATED,
)
def add_questionnaire_template_question(
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: QuestionnaireTemplateQuestionCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireTemplateQuestionRead:
    row = QuestionnaireTemplateService(db).add_question(organization.id, template_id, section_id, payload)
    db.commit()
    db.refresh(row)
    return _question_read(row)
