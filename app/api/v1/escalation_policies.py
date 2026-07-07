import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.escalation_service import EscalationService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.escalation_event import EscalationEvent
from app.models.escalation_policy import EscalationPolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.escalation import (
    EscalationEvaluateResult,
    EscalationEventRead,
    EscalationPolicyCreate,
    EscalationPolicyRead,
    EscalationPolicyUpdate,
)

router = APIRouter(prefix="/compliance/escalation-policies", tags=["escalation-policies"])


def _policy_read(row: EscalationPolicy) -> EscalationPolicyRead:
    return EscalationPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        entity_type=row.entity_type,
        condition_type=row.condition_type,
        condition_value=dict(row.condition_value or {}),
        escalate_to_user_id=row.escalate_to_user_id,
        notification_message_template=row.notification_message_template,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _event_read(row: EscalationEvent) -> EscalationEventRead:
    return EscalationEventRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        escalated_at=row.escalated_at,
        escalated_to=row.escalated_to,
        notification_sent=row.notification_sent,
        notification_queued_at=row.notification_queued_at,
        reason=dict(row.reason) if row.reason else None,
    )


@router.post("", response_model=EscalationPolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: EscalationPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:write")),
) -> EscalationPolicyRead:
    row = EscalationService(db).create_policy(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("", response_model=list[EscalationPolicyRead])
def list_policies(
    entity_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:read")),
) -> list[EscalationPolicyRead]:
    rows = EscalationService(db).list_policies(
        organization.id,
        entity_type=entity_type,
        is_active=is_active,
    )
    return [_policy_read(row) for row in rows]


@router.get("/events", response_model=list[EscalationEventRead])
def list_escalation_events(
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:read")),
) -> list[EscalationEventRead]:
    rows = EscalationService(db).get_escalation_history(
        organization.id,
        entity_type=entity_type,
        entity_id=entity_id,
        skip=skip,
        limit=limit,
    )
    return [_event_read(row) for row in rows]


@router.post("/evaluate", response_model=EscalationEvaluateResult)
def evaluate_policies(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    __: Membership = Depends(require_permission("issues:admin")),
) -> EscalationEvaluateResult:
    result = EscalationService(db).evaluate_policies(organization.id)
    db.commit()
    return EscalationEvaluateResult(**result)


@router.get("/{policy_id}", response_model=EscalationPolicyRead)
def get_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:read")),
) -> EscalationPolicyRead:
    row = EscalationService(db).get_policy(organization.id, policy_id)
    return _policy_read(row)


@router.patch("/{policy_id}", response_model=EscalationPolicyRead)
def update_policy(
    policy_id: uuid.UUID,
    payload: EscalationPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:write")),
) -> EscalationPolicyRead:
    row = EscalationService(db).update_policy(organization.id, policy_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/{policy_id}/deactivate", response_model=EscalationPolicyRead)
def deactivate_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:write")),
) -> EscalationPolicyRead:
    row = EscalationService(db).deactivate_policy(organization.id, policy_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.delete("/{policy_id}", response_model=EscalationPolicyRead)
def delete_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("escalations:write")),
) -> EscalationPolicyRead:
    row = EscalationService(db).soft_delete_policy(organization.id, policy_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _policy_read(row)
