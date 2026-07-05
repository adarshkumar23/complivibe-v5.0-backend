from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.regulatory_alert import RegulatoryChangeAlertRead
from app.services.regulatory_intelligence_service import RegulatoryIntelligenceService

router = APIRouter(prefix="/regulatory-alerts", tags=["regulatory-alerts"])


@router.get("", response_model=list[RegulatoryChangeAlertRead])
def list_regulatory_alerts(
    status: str | None = None,
    framework_code: str | None = None,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[RegulatoryChangeAlertRead]:
    rows = RegulatoryIntelligenceService(db).list_alerts(organization.id, status_filter=status, framework_code=framework_code)
    return [RegulatoryChangeAlertRead.model_validate(row) for row in rows]


@router.post("/{alert_id}/acknowledge", response_model=RegulatoryChangeAlertRead)
def acknowledge_regulatory_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> RegulatoryChangeAlertRead:
    row = RegulatoryIntelligenceService(db).acknowledge_alert(organization.id, alert_id, current_user.id)
    db.commit()
    db.refresh(row)
    return RegulatoryChangeAlertRead.model_validate(row)
