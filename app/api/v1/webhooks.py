import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.webhook_service import WebhookService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_endpoint import WebhookEndpoint
from app.schemas.webhook import (
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
    WebhookEventTypesRead,
    WebhookTestEmitRequest,
)

router = APIRouter(prefix="/compliance/webhook-endpoints", tags=["webhooks"])


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _endpoint_read(row: WebhookEndpoint) -> WebhookEndpointRead:
    return WebhookEndpointRead(
        id=row.id,
        organization_id=row.organization_id,
        url=row.url,
        name=row.name,
        secret=row.secret,
        event_types=list(row.event_types or []),
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _delivery_read(row: WebhookDelivery) -> WebhookDeliveryRead:
    return WebhookDeliveryRead(
        id=row.id,
        organization_id=row.organization_id,
        endpoint_id=row.endpoint_id,
        event_type=row.event_type,
        payload=dict(row.payload or {}),
        payload_hash=row.payload_hash,
        signature=row.signature,
        status=row.status,
        attempts=row.attempts,
        last_attempted_at=row.last_attempted_at,
        response_code=row.response_code,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=WebhookEndpointRead, status_code=status.HTTP_201_CREATED)
def create_endpoint(
    payload: WebhookEndpointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:write")),
) -> WebhookEndpointRead:
    row = WebhookService(db).create_endpoint(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _endpoint_read(row)


@router.get("", response_model=list[WebhookEndpointRead])
def list_endpoints(
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:read")),
) -> list[WebhookEndpointRead]:
    rows = WebhookService(db).list_endpoints(organization.id, is_active=is_active)
    return [_endpoint_read(row) for row in rows]


@router.get("/event-types", response_model=WebhookEventTypesRead)
def list_event_types(
    _: User = Depends(get_current_active_user),
    __: Membership = Depends(require_permission("webhooks:read")),
) -> WebhookEventTypesRead:
    return WebhookEventTypesRead(event_types=WebhookService.list_event_types())


@router.post("/test-emit", response_model=list[WebhookDeliveryRead])
def test_emit(
    payload: WebhookTestEmitRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("webhooks:write")),
) -> list[WebhookDeliveryRead]:
    _require_org_admin(db, membership)
    rows = WebhookService(db).emit(organization.id, payload.event_type, dict(payload.test_payload or {}))
    db.commit()
    for row in rows:
        db.refresh(row)
    return [_delivery_read(row) for row in rows]


@router.get("/{endpoint_id}", response_model=WebhookEndpointRead)
def get_endpoint(
    endpoint_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:read")),
) -> WebhookEndpointRead:
    row = WebhookService(db).get_endpoint(organization.id, endpoint_id)
    return _endpoint_read(row)


@router.patch("/{endpoint_id}", response_model=WebhookEndpointRead)
def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:write")),
) -> WebhookEndpointRead:
    row = WebhookService(db).update_endpoint(organization.id, endpoint_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _endpoint_read(row)


@router.post("/{endpoint_id}/deactivate", response_model=WebhookEndpointRead)
def deactivate_endpoint(
    endpoint_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:write")),
) -> WebhookEndpointRead:
    row = WebhookService(db).deactivate_endpoint(organization.id, endpoint_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _endpoint_read(row)


@router.delete("/{endpoint_id}", response_model=WebhookEndpointRead)
def delete_endpoint(
    endpoint_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:write")),
) -> WebhookEndpointRead:
    row = WebhookService(db).soft_delete_endpoint(organization.id, endpoint_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _endpoint_read(row)


@router.get("/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryRead])
def list_deliveries(
    endpoint_id: uuid.UUID,
    status_value: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:read")),
) -> list[WebhookDeliveryRead]:
    rows = WebhookService(db).get_deliveries(
        organization.id,
        endpoint_id=endpoint_id,
        status_value=status_value,
        limit=limit,
    )
    return [_delivery_read(row) for row in rows]


@router.post("/{endpoint_id}/deliveries/{delivery_id}/deliver", response_model=WebhookDeliveryRead)
def deliver_webhook(
    endpoint_id: uuid.UUID,
    delivery_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("webhooks:write")),
) -> WebhookDeliveryRead:
    service = WebhookService(db)
    delivery = service.get_delivery(organization.id, delivery_id)
    if delivery.endpoint_id != endpoint_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook delivery not found")
    updated = service.deliver(delivery_id)
    db.commit()
    db.refresh(updated)
    return _delivery_read(updated)
