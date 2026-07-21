import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.monitoring import (
    MonitoringReadingCreate,
    MonitoringReadingInboundCreate,
    MonitoringReadingRead,
    ThresholdRegistryRead,
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


@router.get("/threshold-registry", response_model=ThresholdRegistryRead)
def get_threshold_registry(
    ai_system_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> ThresholdRegistryRead:
    """Export every active threshold this organisation enforces.

    Intended for an external collector (or an auditor) that needs to know what core is
    measuring against. Gated on the existing `ai_governance:read` -- it exposes the same
    configuration the monitoring UI already shows, so it needs no new permission, and
    inventing one would leave existing roles unable to read their own thresholds.

    Carries no credential: `api_key_hash` is not a field on ThresholdRegistryEntry, and
    a test asserts the schema's field set to keep it that way.
    """
    payload = AIMonitoringService(db).build_threshold_registry(organization.id, ai_system_id=ai_system_id)
    return ThresholdRegistryRead.model_validate(payload)
