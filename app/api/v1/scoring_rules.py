import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.questionnaire_scoring_rule import QuestionnaireScoringRule
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.user import User
from app.schemas.questionnaire import QuestionnaireRuleCreate, QuestionnaireRuleRead, QuestionnaireRuleUpdate
from app.services.audit_service import AuditService
from app.services.seed_service import SeedService

router = APIRouter(prefix="/compliance/questionnaire-scoring-rules", tags=["questionnaire-scoring-rules"])


def _rule_read(row: QuestionnaireScoringRule) -> QuestionnaireRuleRead:
    return QuestionnaireRuleRead(
        id=row.id,
        organization_id=row.organization_id,
        template_id=row.template_id,
        question_id=row.question_id,
        rule_name=row.rule_name,
        condition_operator=row.condition_operator,
        condition_value=row.condition_value,
        score_delta=row.score_delta,
        rationale=row.rationale,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_visible_template(db: Session, org_id: uuid.UUID, template_id: uuid.UUID) -> QuestionnaireTemplate:
    row = db.execute(
        select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.id == template_id,
            QuestionnaireTemplate.deleted_at.is_(None),
            (QuestionnaireTemplate.organization_id == org_id) | QuestionnaireTemplate.organization_id.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")
    return row


def _require_question_in_template(db: Session, template_id: uuid.UUID, question_id: uuid.UUID) -> QuestionnaireTemplateQuestion:
    row = db.execute(
        select(QuestionnaireTemplateQuestion).where(
            QuestionnaireTemplateQuestion.id == question_id,
            QuestionnaireTemplateQuestion.template_id == template_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="question_id not found for template")
    return row


def _require_rule_visible(db: Session, org_id: uuid.UUID, rule_id: uuid.UUID) -> QuestionnaireScoringRule:
    row = db.execute(
        select(QuestionnaireScoringRule).where(
            QuestionnaireScoringRule.id == rule_id,
            (QuestionnaireScoringRule.organization_id == org_id) | QuestionnaireScoringRule.organization_id.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scoring rule not found")
    return row


@router.get("", response_model=list[QuestionnaireRuleRead])
def list_scoring_rules(
    template_id: uuid.UUID | None = Query(default=None),
    question_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[QuestionnaireRuleRead]:
    SeedService.ensure_questionnaire_scoring_rules(db)
    stmt = select(QuestionnaireScoringRule).where(
        (QuestionnaireScoringRule.organization_id == organization.id) | QuestionnaireScoringRule.organization_id.is_(None)
    )
    if template_id is not None:
        stmt = stmt.where(QuestionnaireScoringRule.template_id == template_id)
    if question_id is not None:
        stmt = stmt.where(QuestionnaireScoringRule.question_id == question_id)
    if not include_inactive:
        stmt = stmt.where(QuestionnaireScoringRule.is_active.is_(True))

    rows = db.execute(
        stmt.order_by(QuestionnaireScoringRule.organization_id.desc(), QuestionnaireScoringRule.created_at.desc())
    ).scalars().all()
    return [_rule_read(row) for row in rows]


@router.post("", response_model=QuestionnaireRuleRead, status_code=status.HTTP_201_CREATED)
def create_scoring_rule(
    payload: QuestionnaireRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireRuleRead:
    _ = _require_visible_template(db, organization.id, payload.template_id)
    _ = _require_question_in_template(db, payload.template_id, payload.question_id)

    row = QuestionnaireScoringRule(
        organization_id=organization.id,
        template_id=payload.template_id,
        question_id=payload.question_id,
        rule_name=payload.rule_name,
        condition_operator=payload.condition_operator,
        condition_value=payload.condition_value,
        score_delta=payload.score_delta,
        rationale=payload.rationale,
        is_active=True,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="scoring_rule.created",
        entity_type="questionnaire_scoring_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "template_id": str(row.template_id),
            "question_id": str(row.question_id),
            "condition_operator": row.condition_operator,
            "condition_value": row.condition_value,
            "score_delta": row.score_delta,
        },
        metadata_json={"source": "api"},
    )

    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.patch("/{rule_id}", response_model=QuestionnaireRuleRead)
def update_scoring_rule(
    rule_id: uuid.UUID,
    payload: QuestionnaireRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireRuleRead:
    row = _require_rule_visible(db, organization.id, rule_id)
    if row.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System scoring rules cannot be modified")

    before = {
        "rule_name": row.rule_name,
        "condition_operator": row.condition_operator,
        "condition_value": row.condition_value,
        "score_delta": row.score_delta,
        "is_active": row.is_active,
    }

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="scoring_rule.updated",
        entity_type="questionnaire_scoring_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "rule_name": row.rule_name,
            "condition_operator": row.condition_operator,
            "condition_value": row.condition_value,
            "score_delta": row.score_delta,
            "is_active": row.is_active,
        },
        metadata_json={"source": "api"},
    )

    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.delete("/{rule_id}", response_model=QuestionnaireRuleRead)
def deactivate_scoring_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> QuestionnaireRuleRead:
    row = _require_rule_visible(db, organization.id, rule_id)
    if row.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System scoring rules cannot be deactivated")

    row.is_active = False
    db.flush()

    AuditService(db).write_audit_log(
        action="scoring_rule.deactivated",
        entity_type="questionnaire_scoring_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"is_active": row.is_active},
        metadata_json={"source": "api"},
    )

    db.commit()
    db.refresh(row)
    return _rule_read(row)


@router.get("/template/{template_id}", response_model=list[QuestionnaireRuleRead])
def list_template_scoring_rules(
    template_id: uuid.UUID,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[QuestionnaireRuleRead]:
    SeedService.ensure_questionnaire_scoring_rules(db)
    _ = _require_visible_template(db, organization.id, template_id)

    stmt = select(QuestionnaireScoringRule).where(
        QuestionnaireScoringRule.template_id == template_id,
        (QuestionnaireScoringRule.organization_id == organization.id) | QuestionnaireScoringRule.organization_id.is_(None),
    )
    if not include_inactive:
        stmt = stmt.where(QuestionnaireScoringRule.is_active.is_(True))

    rows = db.execute(
        stmt.order_by(QuestionnaireScoringRule.organization_id.desc(), QuestionnaireScoringRule.created_at.desc())
    ).scalars().all()
    return [_rule_read(row) for row in rows]
