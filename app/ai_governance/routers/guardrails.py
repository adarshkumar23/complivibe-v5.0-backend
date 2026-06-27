import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.guardrails_envelopes import (
    GuardrailCreate,
    GuardrailEventRead,
    GuardrailRead,
)
from app.ai_governance.services.guardrail_service import GuardrailService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/guardrails", tags=["ai-governance-guardrails"])
events_router = APIRouter(prefix="/ai-governance", tags=["ai-governance-guardrails"])


@router.post("", response_model=GuardrailRead, status_code=status.HTTP_201_CREATED)
def create_org_guardrail(
    payload: GuardrailCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_membership: Membership = Depends(require_permission("ai_governance:write")),
) -> GuardrailRead:
    row = GuardrailService(db).create_guardrail(organization.id, payload, current_membership.user_id)
    db.commit()
    db.refresh(row)
    return GuardrailRead.model_validate(row)


@router.get("", response_model=list[GuardrailRead])
def list_org_guardrails(
    system_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    guardrail_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[GuardrailRead]:
    rows = GuardrailService(db).list_guardrails(
        organization.id,
        system_id=system_id,
        is_active=is_active,
        guardrail_type=guardrail_type,
    )
    return [GuardrailRead.model_validate(row) for row in rows]


@router.get("/events", response_model=list[GuardrailEventRead])
def list_guardrail_events(
    system_id: uuid.UUID | None = Query(default=None),
    guardrail_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[GuardrailEventRead]:
    rows = GuardrailService(db).get_guardrail_events(
        organization.id,
        system_id=system_id,
        guardrail_id=guardrail_id,
        event_type=event_type,
        limit=limit,
    )
    return [GuardrailEventRead.model_validate(row) for row in rows]


@events_router.get("/guardrail-events", response_model=list[GuardrailEventRead])
def list_guardrail_events_alias(
    system_id: uuid.UUID | None = Query(default=None),
    guardrail_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[GuardrailEventRead]:
    rows = GuardrailService(db).get_guardrail_events(
        organization.id,
        system_id=system_id,
        guardrail_id=guardrail_id,
        event_type=event_type,
        limit=limit,
    )
    return [GuardrailEventRead.model_validate(row) for row in rows]
