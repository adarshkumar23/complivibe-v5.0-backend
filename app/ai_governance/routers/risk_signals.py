import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai_governance.schemas.signals_recommendations_diagnostics import AIRiskSignalRead
from app.ai_governance.services.signal_service import SignalService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/risk-signals", tags=["ai-governance-risk-signals"])


@router.get("", response_model=list[AIRiskSignalRead])
def list_org_risk_signals(
    system_id: uuid.UUID | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIRiskSignalRead]:
    rows = SignalService(db).list_signals(
        organization.id,
        system_id=system_id,
        signal_type=signal_type,
        status_value=status_value,
        severity=severity,
        skip=skip,
        limit=limit,
    )
    return [AIRiskSignalRead.model_validate(row) for row in rows]
