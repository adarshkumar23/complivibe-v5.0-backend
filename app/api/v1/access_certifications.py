import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.access_certification import AccessCertificationCampaign, AccessCertificationItem
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.access_certification import (
    AccessCertificationCampaignCreate,
    AccessCertificationCampaignDetail,
    AccessCertificationCampaignRead,
    AccessCertificationCampaignUpdate,
    AccessCertificationDecisionSubmit,
    AccessCertificationItemRead,
)
from app.services.access_certification_service import AccessCertificationService

router = APIRouter(prefix="/access-certifications", tags=["access-certifications"])


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _item_read(row: AccessCertificationItem) -> AccessCertificationItemRead:
    return AccessCertificationItemRead(
        id=row.id,
        organization_id=row.organization_id,
        campaign_id=row.campaign_id,
        user_id=row.user_id,
        reviewer_user_id=row.reviewer_user_id,
        system_key=row.system_key,
        system_name=row.system_name,
        access_level=row.access_level,
        status=row.status,
        decision=row.decision,
        decision_comment=row.decision_comment,
        decided_by_user_id=row.decided_by_user_id,
        decided_at=row.decided_at,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _campaign_read(service: AccessCertificationService, row: AccessCertificationCampaign) -> AccessCertificationCampaignRead:
    return AccessCertificationCampaignRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        scope_type=row.scope_type,
        scope_config_json=row.scope_config_json,
        status=row.status,
        due_date=row.due_date,
        launched_at=row.launched_at,
        completed_at=row.completed_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        **service.campaign_counts(row.organization_id, row.id),
    )


def _campaign_detail(service: AccessCertificationService, row: AccessCertificationCampaign) -> AccessCertificationCampaignDetail:
    base = _campaign_read(service, row).model_dump()
    items = [_item_read(item) for item in service.list_items_for_campaign(row.organization_id, row.id)]
    return AccessCertificationCampaignDetail(**base, items=items)


@router.post("/campaigns", response_model=AccessCertificationCampaignDetail, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: AccessCertificationCampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> AccessCertificationCampaignDetail:
    service = AccessCertificationService(db)
    row = service.create_campaign(
        organization_id=organization.id,
        payload=payload,
        actor_user_id=current_user.id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _campaign_detail(service, row)


@router.get("/campaigns", response_model=list[AccessCertificationCampaignRead])
def list_campaigns(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> list[AccessCertificationCampaignRead]:
    service = AccessCertificationService(db)
    return [_campaign_read(service, row) for row in service.list_campaigns(organization.id, include_archived=include_archived)]


@router.get("/campaigns/{campaign_id}", response_model=AccessCertificationCampaignDetail)
def get_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> AccessCertificationCampaignDetail:
    service = AccessCertificationService(db)
    row = service.get_campaign(organization.id, campaign_id)
    return _campaign_detail(service, row)


@router.patch("/campaigns/{campaign_id}", response_model=AccessCertificationCampaignRead)
def update_campaign(
    campaign_id: uuid.UUID,
    payload: AccessCertificationCampaignUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> AccessCertificationCampaignRead:
    service = AccessCertificationService(db)
    row = service.get_campaign(organization.id, campaign_id)
    row = service.update_campaign(
        campaign=row,
        payload=payload,
        actor_user_id=current_user.id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _campaign_read(service, row)


@router.delete("/campaigns/{campaign_id}", response_model=AccessCertificationCampaignRead)
def archive_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> AccessCertificationCampaignRead:
    service = AccessCertificationService(db)
    row = service.get_campaign(organization.id, campaign_id)
    row = service.archive_campaign(
        campaign=row,
        actor_user_id=current_user.id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _campaign_read(service, row)


@router.get("/my-certifications", response_model=list[AccessCertificationItemRead])
def my_certifications(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:read")),
) -> list[AccessCertificationItemRead]:
    service = AccessCertificationService(db)
    rows = service.list_my_certifications(organization.id, current_user.id, status_filter=status_filter)
    return [_item_read(row) for row in rows]


@router.post("/items/{item_id}/decision", response_model=AccessCertificationItemRead)
def submit_decision(
    item_id: uuid.UUID,
    payload: AccessCertificationDecisionSubmit,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("recertification:write")),
) -> AccessCertificationItemRead:
    service = AccessCertificationService(db)
    item = service.get_item(organization.id, item_id)
    campaign = service.get_campaign(organization.id, item.campaign_id)
    item = service.submit_decision(
        item=item,
        campaign=campaign,
        payload=payload,
        actor_user_id=current_user.id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(item)
    return _item_read(item)
