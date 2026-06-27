import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.monitoring import (
    MonitoringReadingCreate,
    MonitoringReadingInboundCreate,
    MonitoringReadingRead,
)
from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/monitoring", tags=["ai-governance-monitoring"])
inbound_router = APIRouter(prefix="/ai-monitoring", tags=["ai-monitoring"])


@router.post("/readings", response_model=MonitoringReadingRead, status_code=status.HTTP_201_CREATED)
def submit_monitoring_reading(
    payload: MonitoringReadingCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> MonitoringReadingRead:
    row = AIMonitoringService(db).submit_reading(
        organization.id,
        payload.config_id,
        payload.value,
        reading_source="manual",
        source_tool=payload.source_tool,
    )
    db.commit()
    db.refresh(row)
    return MonitoringReadingRead.model_validate(row)


@inbound_router.post("/readings", response_model=MonitoringReadingRead, status_code=status.HTTP_201_CREATED)
def receive_inbound_monitoring_reading(
    payload: MonitoringReadingInboundCreate,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> MonitoringReadingRead:
    row = AIMonitoringService(db).receive_inbound_reading(
        raw_key=x_complivibe_key or "",
        config_id=payload.config_id,
        value=payload.value,
        source_tool=payload.source_tool,
        metric_type=payload.metric_type,
    )
    db.commit()
    db.refresh(row)
    return MonitoringReadingRead.model_validate(row)
