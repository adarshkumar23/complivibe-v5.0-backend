import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai_governance.schemas.signals_recommendations_diagnostics import AIGovEventRead, AIGovEventSummaryRead
from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance", tags=["ai-governance-diagnostics"])


@router.get("/events", response_model=list[AIGovEventRead])
def list_org_events(
    event_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIGovEventRead]:
    rows = AIGovernanceEventService.get_org_events(
        db,
        organization.id,
        event_type=event_type,
        from_date=from_date,
        to_date=to_date,
        skip=skip,
        limit=limit,
    )
    return [AIGovEventRead.model_validate(row) for row in rows]


@router.get("/events/summary", response_model=AIGovEventSummaryRead)
def get_events_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIGovEventSummaryRead:
    payload = AIGovernanceEventService.get_event_summary(db, organization.id)
    return AIGovEventSummaryRead(**payload)
