import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.inbound_questionnaire_service import InboundQuestionnaireService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.inbound_questionnaire_item import InboundQuestionnaireItem
from app.models.inbound_questionnaire_session import InboundQuestionnaireSession
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.questionnaire import (
    InboundQuestionnaireBulkAddResult,
    InboundQuestionnaireBulkItemCreate,
    InboundQuestionnaireDraftAllResult,
    InboundQuestionnaireItemCreate,
    InboundQuestionnaireItemRead,
    InboundQuestionnaireReviewRequest,
    InboundQuestionnaireSessionCreate,
    InboundQuestionnaireSessionRead,
    InboundQuestionnaireSessionSummary,
)

router = APIRouter(prefix="/compliance/inbound-questionnaires", tags=["inbound-questionnaires"])


def _session_read(row: InboundQuestionnaireSession) -> InboundQuestionnaireSessionRead:
    return InboundQuestionnaireSessionRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        sender_name=row.sender_name,
        sender_email=row.sender_email,
        description=row.description,
        due_date=row.due_date,
        status=row.status,
        total_questions=row.total_questions,
        drafted_count=row.drafted_count,
        approved_count=row.approved_count,
        sent_count=row.sent_count,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _item_read(row: InboundQuestionnaireItem) -> InboundQuestionnaireItemRead:
    return InboundQuestionnaireItemRead(
        id=row.id,
        organization_id=row.organization_id,
        session_id=row.session_id,
        question_text=row.question_text,
        question_type=row.question_type,
        category_tag=row.category_tag,
        framework_ref=row.framework_ref,
        order_index=row.order_index,
        suggested_answer_text=row.suggested_answer_text,
        source_type=row.source_type,
        source_id=row.source_id,
        source_title=row.source_title,
        source_excerpt=row.source_excerpt,
        source_date=row.source_date,
        confidence_score=row.confidence_score,
        confidence_reason=row.confidence_reason,
        requires_human_review=row.requires_human_review,
        status=row.status,
        final_answer_text=row.final_answer_text,
        reviewer_id=row.reviewer_id,
        reviewed_at=row.reviewed_at,
        review_notes=row.review_notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=InboundQuestionnaireSessionRead, status_code=status.HTTP_201_CREATED)
def create_inbound_session(
    payload: InboundQuestionnaireSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireSessionRead:
    row = InboundQuestionnaireService(db).create_session(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _session_read(row)


@router.get("", response_model=list[InboundQuestionnaireSessionRead])
def list_inbound_sessions(
    status_value: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[InboundQuestionnaireSessionRead]:
    rows = InboundQuestionnaireService(db).list_sessions(
        organization.id,
        status_value=status_value,
        skip=skip,
        limit=limit,
    )
    return [_session_read(row) for row in rows]


@router.get("/{session_id}", response_model=InboundQuestionnaireSessionRead)
def get_inbound_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> InboundQuestionnaireSessionRead:
    row = InboundQuestionnaireService(db).get_session(organization.id, session_id)
    return _session_read(row)


@router.delete("/{session_id}", response_model=InboundQuestionnaireSessionRead)
def soft_delete_inbound_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireSessionRead:
    row = InboundQuestionnaireService(db).soft_delete_session(organization.id, session_id, user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return _session_read(row)


@router.get("/{session_id}/summary", response_model=InboundQuestionnaireSessionSummary)
def inbound_session_summary(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> InboundQuestionnaireSessionSummary:
    payload = InboundQuestionnaireService(db).get_session_summary(organization.id, session_id)
    return InboundQuestionnaireSessionSummary(**payload)


@router.post("/{session_id}/items", response_model=InboundQuestionnaireItemRead, status_code=status.HTTP_201_CREATED)
def add_inbound_item(
    session_id: uuid.UUID,
    payload: InboundQuestionnaireItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireItemRead:
    row = InboundQuestionnaireService(db).add_item(organization.id, session_id, payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return _item_read(row)


@router.post("/{session_id}/items/bulk", response_model=InboundQuestionnaireBulkAddResult)
def bulk_add_inbound_items(
    session_id: uuid.UUID,
    payload: InboundQuestionnaireBulkItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireBulkAddResult:
    result = InboundQuestionnaireService(db).bulk_add_items(
        organization.id,
        session_id,
        payload.items,
        actor_user_id=current_user.id,
    )
    db.commit()
    return InboundQuestionnaireBulkAddResult(**result)


@router.get("/{session_id}/items", response_model=list[InboundQuestionnaireItemRead])
def list_inbound_items(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[InboundQuestionnaireItemRead]:
    rows = InboundQuestionnaireService(db).list_items(organization.id, session_id)
    return [_item_read(row) for row in rows]


@router.get("/{session_id}/items/{item_id}", response_model=InboundQuestionnaireItemRead)
def get_inbound_item(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> InboundQuestionnaireItemRead:
    row = InboundQuestionnaireService(db).get_item(organization.id, session_id, item_id)
    return _item_read(row)


@router.post("/{session_id}/items/{item_id}/draft", response_model=InboundQuestionnaireItemRead)
def draft_inbound_item(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireItemRead:
    row = InboundQuestionnaireService(db).draft_item(
        organization.id,
        session_id,
        item_id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _item_read(row)


@router.post("/{session_id}/draft-all", response_model=InboundQuestionnaireDraftAllResult)
def draft_all_inbound_items(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireDraftAllResult:
    result = InboundQuestionnaireService(db).draft_all_items(
        organization.id,
        session_id,
        actor_user_id=current_user.id,
    )
    db.commit()
    return InboundQuestionnaireDraftAllResult(**result)


@router.post("/{session_id}/items/{item_id}/review", response_model=InboundQuestionnaireItemRead)
def review_inbound_item(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: InboundQuestionnaireReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireItemRead:
    row = InboundQuestionnaireService(db).review_item(
        organization.id,
        session_id,
        item_id,
        action=payload.action,
        reviewer_id=current_user.id,
        review_notes=payload.review_notes,
        edited_answer=payload.edited_answer,
    )
    db.commit()
    db.refresh(row)
    return _item_read(row)


@router.post("/{session_id}/items/{item_id}/mark-sent", response_model=InboundQuestionnaireItemRead)
def mark_inbound_item_sent(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireItemRead:
    row = InboundQuestionnaireService(db).mark_item_sent(
        organization.id,
        session_id,
        item_id,
        user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _item_read(row)


@router.post("/{session_id}/complete", response_model=InboundQuestionnaireSessionRead)
def complete_inbound_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> InboundQuestionnaireSessionRead:
    row = InboundQuestionnaireService(db).mark_session_completed(
        organization.id,
        session_id,
        user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _session_read(row)
