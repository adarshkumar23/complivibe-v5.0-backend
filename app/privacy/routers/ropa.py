import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.ropa import (
    Article30ReportRead,
    ProcessingActivityCreate,
    ProcessingActivityRead,
    ProcessingActivityUpdate,
    RopaFrameworkLinkCreate,
    RopaFrameworkLinkRead,
    RopaSummaryRead,
)
from app.privacy.services.ropa_service import RopaService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/privacy/ropa", tags=["privacy-ropa"])


def _activity_read(service: RopaService, row) -> ProcessingActivityRead:
    return ProcessingActivityRead.model_validate(service.activity_response_payload(row))


@router.post("/activities", response_model=ProcessingActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: ProcessingActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> ProcessingActivityRead:
    service = RopaService(db)
    row = service.create_activity(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _activity_read(service, row)


@router.get("/activities", response_model=list[ProcessingActivityRead])
def list_activities(
    status_filter: str | None = Query(default=None, alias="status"),
    legal_basis: str | None = Query(default=None),
    requires_dpia: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[ProcessingActivityRead]:
    service = RopaService(db)
    rows = service.list_activities(
        organization.id,
        status_filter=status_filter,
        legal_basis=legal_basis,
        requires_dpia=requires_dpia,
        skip=skip,
        limit=limit,
    )
    return [_activity_read(service, row) for row in rows]


@router.get("/activities/summary", response_model=RopaSummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> RopaSummaryRead:
    return RopaSummaryRead.model_validate(RopaService(db).get_ropa_summary(organization.id))


@router.get("/activities/{activity_id}", response_model=ProcessingActivityRead)
def get_activity(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> ProcessingActivityRead:
    service = RopaService(db)
    return _activity_read(service, service.get_activity(organization.id, activity_id))


@router.patch("/activities/{activity_id}", response_model=ProcessingActivityRead)
def update_activity(
    activity_id: uuid.UUID,
    payload: ProcessingActivityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> ProcessingActivityRead:
    service = RopaService(db)
    row = service.update_activity(organization.id, activity_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _activity_read(service, row)


@router.delete("/activities/{activity_id}", response_model=ProcessingActivityRead)
def delete_activity(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> ProcessingActivityRead:
    service = RopaService(db)
    row = service.soft_delete_activity(organization.id, activity_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _activity_read(service, row)


@router.post("/activities/{activity_id}/obligation-links", response_model=RopaFrameworkLinkRead, status_code=status.HTTP_201_CREATED)
def link_obligation(
    activity_id: uuid.UUID,
    payload: RopaFrameworkLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> RopaFrameworkLinkRead:
    row = RopaService(db).link_obligation(organization.id, activity_id, payload.obligation_id, current_user.id)
    db.commit()
    links = RopaService(db).get_activity_obligations(organization.id, activity_id)
    match = next(item for item in links if item["id"] == str(row.id))
    return RopaFrameworkLinkRead.model_validate(match)


@router.delete("/activities/{activity_id}/obligation-links/{obligation_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_obligation(
    activity_id: uuid.UUID,
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> None:
    RopaService(db).unlink_obligation(organization.id, activity_id, obligation_id, current_user.id)
    db.commit()
    return None


@router.get("/activities/{activity_id}/obligation-links", response_model=list[RopaFrameworkLinkRead])
def list_obligation_links(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[RopaFrameworkLinkRead]:
    return [RopaFrameworkLinkRead.model_validate(item) for item in RopaService(db).get_activity_obligations(organization.id, activity_id)]


@router.get("/article30-report", response_model=Article30ReportRead)
def article30_report(
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("privacy:read")),
    organization: Organization = Depends(get_current_organization),
) -> Article30ReportRead:
    payload = RopaService(db).generate_article30_report(organization.id)
    AuditService(db).write_audit_log(
        action="ropa.article30_exported",
        entity_type="processing_activity",
        entity_id=None,
        organization_id=organization.id,
        actor_user_id=membership.user_id,
        after_json={"total_activities": payload.get("total_activities", 0), "status": payload.get("status")},
        metadata_json={"source": "api"},
    )
    db.commit()
    return Article30ReportRead.model_validate(payload)
