import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.incidents import (
    DataIncidentCreate,
    DataIncidentRead,
    DataIncidentSummaryRead,
    EscalateIncidentRead,
    ResolveIncidentRequest,
)
from app.data_observability.services.incident_detection_service import DataIncidentService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/incidents", tags=["data-observability-incidents"])


def _incident_read(service: DataIncidentService, row) -> DataIncidentRead:
    return DataIncidentRead.model_validate(service.incident_response_payload(row))


@router.post("", response_model=DataIncidentRead, status_code=status.HTTP_201_CREATED)
def create_manual_incident(
    payload: DataIncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataIncidentRead:
    service = DataIncidentService(db)
    row = service.create_incident(
        organization.id,
        payload.data_asset_id,
        detector_type=payload.detector_type,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        rule_type=payload.rule_type,
        detector_ref_id=payload.detector_ref_id,
        evidence=payload.evidence_json,
        detected_by=payload.detected_by,
        actor_user_id=current_user.id,
    )
    assert row is not None
    db.commit()
    db.refresh(row)
    return _incident_read(service, row)


@router.get("", response_model=list[DataIncidentRead])
def list_incidents(
    data_asset_id: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    detector_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataIncidentRead]:
    service = DataIncidentService(db)
    rows = service.list_incidents(
        organization.id,
        data_asset_id=data_asset_id,
        severity=severity,
        status_filter=status_filter,
        detector_type=detector_type,
        skip=skip,
        limit=limit,
    )
    return [_incident_read(service, row) for row in rows]


@router.get("/summary", response_model=DataIncidentSummaryRead)
def get_incident_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataIncidentSummaryRead:
    payload = DataIncidentService(db).get_incident_summary(organization.id)
    return DataIncidentSummaryRead.model_validate(payload)


@router.get("/{incident_id}", response_model=DataIncidentRead)
def get_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> DataIncidentRead:
    service = DataIncidentService(db)
    row = service.get_incident(organization.id, incident_id)
    return _incident_read(service, row)


@router.post("/{incident_id}/investigate", response_model=DataIncidentRead)
def investigate_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataIncidentRead:
    service = DataIncidentService(db)
    row = service.investigate_incident(organization.id, incident_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _incident_read(service, row)


@router.post("/{incident_id}/contain", response_model=DataIncidentRead)
def contain_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataIncidentRead:
    service = DataIncidentService(db)
    row = service.contain_incident(organization.id, incident_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _incident_read(service, row)


@router.post("/{incident_id}/resolve", response_model=DataIncidentRead)
def resolve_incident(
    incident_id: uuid.UUID,
    payload: ResolveIncidentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataIncidentRead:
    service = DataIncidentService(db)
    row = service.resolve_incident(organization.id, incident_id, current_user.id, notes=payload.notes)
    db.commit()
    db.refresh(row)
    return _incident_read(service, row)


@router.post("/{incident_id}/dismiss", response_model=DataIncidentRead)
def dismiss_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataIncidentRead:
    service = DataIncidentService(db)
    row = service.dismiss_incident(organization.id, incident_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _incident_read(service, row)


@router.post("/{incident_id}/escalate-to-issue", response_model=EscalateIncidentRead)
def escalate_incident_to_issue(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> EscalateIncidentRead:
    issue = DataIncidentService(db).escalate_to_issue(organization.id, incident_id, current_user.id)
    db.commit()
    return EscalateIncidentRead(issue_id=issue.id, incident_id=incident_id)
