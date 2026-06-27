import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.access_monitoring import (
    DataAccessAnomalyRuleCreate,
    DataAccessAnomalyRuleRead,
    DataAccessAnomalyRuleUpdate,
    DataAccessEventIngest,
    DataAccessLogRead,
    DataAccessSummaryRead,
)
from app.data_observability.services.access_monitoring_service import AccessMonitoringService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/access", tags=["data-observability-access"])


@router.post("/events", response_model=DataAccessLogRead, status_code=status.HTTP_201_CREATED)
def ingest_access_event(
    payload: DataAccessEventIngest,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> DataAccessLogRead:
    service = AccessMonitoringService(db)
    org_id = service.resolve_org_by_api_key(x_complivibe_key or "")
    row = service.log_access_event(org_id, payload.data_asset_id, payload)
    db.commit()
    db.refresh(row)
    return DataAccessLogRead.model_validate(row)


@router.get("/logs", response_model=list[DataAccessLogRead])
def list_access_logs(
    data_asset_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    access_type: str | None = Query(default=None),
    access_result: str | None = Query(default=None),
    from_time: datetime | None = Query(default=None),
    to_time: datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataAccessLogRead]:
    rows = AccessMonitoringService(db).list_access_logs(
        organization.id,
        data_asset_id=data_asset_id,
        actor_id=actor_id,
        access_type=access_type,
        access_result=access_result,
        from_time=from_time,
        to_time=to_time,
        skip=skip,
        limit=limit,
    )
    return [DataAccessLogRead.model_validate(row) for row in rows]


@router.get("/summary", response_model=DataAccessSummaryRead)
def get_access_summary(
    data_asset_id: uuid.UUID | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataAccessSummaryRead:
    payload = AccessMonitoringService(db).get_access_summary(organization.id, data_asset_id=data_asset_id, days=days)
    return DataAccessSummaryRead.model_validate(payload)


@router.get("/anomaly-rules", response_model=list[DataAccessAnomalyRuleRead])
def list_anomaly_rules(
    data_asset_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataAccessAnomalyRuleRead]:
    rows = AccessMonitoringService(db).list_anomaly_rules(organization.id, data_asset_id=data_asset_id)
    return [DataAccessAnomalyRuleRead.model_validate(row) for row in rows]


@router.post("/anomaly-rules", response_model=DataAccessAnomalyRuleRead, status_code=status.HTTP_201_CREATED)
def create_anomaly_rule(
    payload: DataAccessAnomalyRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAccessAnomalyRuleRead:
    row = AccessMonitoringService(db).create_anomaly_rule(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DataAccessAnomalyRuleRead.model_validate(row)


@router.patch("/anomaly-rules/{rule_id}", response_model=DataAccessAnomalyRuleRead)
def update_anomaly_rule(
    rule_id: uuid.UUID,
    payload: DataAccessAnomalyRuleUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAccessAnomalyRuleRead:
    row = AccessMonitoringService(db).update_anomaly_rule(organization.id, rule_id, payload)
    db.commit()
    db.refresh(row)
    return DataAccessAnomalyRuleRead.model_validate(row)


@router.post("/anomaly-rules/{rule_id}/deactivate", response_model=DataAccessAnomalyRuleRead)
def deactivate_anomaly_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataAccessAnomalyRuleRead:
    row = AccessMonitoringService(db).deactivate_rule(organization.id, rule_id, current_user.id)
    db.commit()
    db.refresh(row)
    return DataAccessAnomalyRuleRead.model_validate(row)
