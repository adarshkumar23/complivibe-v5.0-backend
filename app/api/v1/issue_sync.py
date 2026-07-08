from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.issue_sync import (
    IssueSyncCommentRead,
    IssueSyncConnectionCreate,
    IssueSyncConnectionRead,
    IssueSyncConnectionUpdate,
    IssueSyncEventRead,
    IssueSyncLinkCreate,
    IssueSyncLinkRead,
    IssueSyncOutboundRequest,
    IssueSyncWebhookResponse,
)
from app.services.issue_sync_service import IssueSyncService

router = APIRouter(prefix="/issue-sync", tags=["issue-sync"])


def _connection_read(row, service: IssueSyncService) -> IssueSyncConnectionRead:
    return IssueSyncConnectionRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        name=row.name,
        provider=row.provider,
        entity_type=row.entity_type,
        direction_mode=row.direction_mode,
        is_active=row.is_active,
        project_ref=row.project_ref,
        api_base_url=row.api_base_url,
        credentials_json=row.credentials_json or {},
        webhook_secret=row.webhook_secret,
        field_mapping_json=row.field_mapping_json or {},
        created_by=row.created_by,
        context_flags=service.describe_connection_context(row),
    )


def _link_read(row) -> IssueSyncLinkRead:
    return IssueSyncLinkRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        connection_id=row.connection_id,
        entity_type=row.entity_type,
        internal_entity_id=row.internal_entity_id,
        external_entity_id=row.external_entity_id,
        external_key=row.external_key,
        last_synced_at=row.last_synced_at,
        last_status=row.last_status,
    )


def _event_read(row) -> IssueSyncEventRead:
    return IssueSyncEventRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        connection_id=row.connection_id,
        provider=row.provider,
        direction=row.direction,
        entity_type=row.entity_type,
        event_type=row.event_type,
        external_event_id=row.external_event_id,
        status=row.status,
        payload_json=row.payload_json or {},
        error_message=row.error_message,
        processed_at=row.processed_at,
    )


def _comment_read(row) -> IssueSyncCommentRead:
    return IssueSyncCommentRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        issue_id=row.issue_id,
        provider=row.provider,
        direction=row.direction,
        external_comment_id=row.external_comment_id,
        body=row.body,
        author_ref=row.author_ref,
        created_by_user_id=row.created_by_user_id,
    )


@router.post("/connections", response_model=IssueSyncConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: IssueSyncConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_connection:create")),
) -> IssueSyncConnectionRead:
    service = IssueSyncService(db)
    row = service.create_connection(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _connection_read(row, service)


@router.get("/connections", response_model=list[IssueSyncConnectionRead])
def list_connections(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_connection:list")),
) -> list[IssueSyncConnectionRead]:
    service = IssueSyncService(db)
    rows = service.list_connections(organization.id)
    return [_connection_read(row, service) for row in rows]


@router.patch("/connections/{connection_id}", response_model=IssueSyncConnectionRead)
def update_connection(
    connection_id: uuid.UUID,
    payload: IssueSyncConnectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_connection:update")),
) -> IssueSyncConnectionRead:
    service = IssueSyncService(db)
    row = service.update_connection(organization.id, connection_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _connection_read(row, service)


@router.post("/connections/{connection_id}/links", response_model=IssueSyncLinkRead, status_code=status.HTTP_201_CREATED)
def create_link(
    connection_id: uuid.UUID,
    payload: IssueSyncLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_link:create")),
) -> IssueSyncLinkRead:
    row = IssueSyncService(db).upsert_link(organization.id, connection_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _link_read(row)


@router.post("/connections/{connection_id}/sync/outbound", response_model=IssueSyncEventRead)
def run_outbound_sync(
    connection_id: uuid.UUID,
    payload: IssueSyncOutboundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_outbound:run")),
) -> IssueSyncEventRead:
    row = IssueSyncService(db).run_outbound_sync(
        org_id=organization.id,
        actor_user_id=current_user.id,
        connection_id=connection_id,
        payload=payload,
    )
    db.commit()
    db.refresh(row)
    return _event_read(row)


async def _parse_webhook_body(request: Request) -> tuple[bytes, dict[str, Any]]:
    raw_body = await request.body()
    if not raw_body:
        return raw_body, {}
    try:
        parsed = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid JSON body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Webhook body must be a JSON object")
    return raw_body, parsed


@router.post("/webhooks/jira/{connection_id}", response_model=IssueSyncWebhookResponse)
async def ingest_jira_webhook(
    connection_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_webhook:jira")),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    x_atlassian_webhook_identifier: str | None = Header(default=None, alias="X-Atlassian-Webhook-Identifier"),
    secret: str | None = Query(default=None),
) -> IssueSyncWebhookResponse:
    _raw_body, payload = await _parse_webhook_body(request)
    row, is_duplicate = IssueSyncService(db).ingest_jira_webhook(
        org_id=organization.id,
        connection_id=connection_id,
        webhook_identifier=x_atlassian_webhook_identifier,
        payload=payload,
        provided_secret=x_webhook_secret or secret,
    )
    db.commit()
    detail = "duplicate jira webhook delivery ignored" if is_duplicate else "jira webhook processed"
    return IssueSyncWebhookResponse(processed=True, event_id=row.id, status=row.status, detail=detail, duplicate_delivery=is_duplicate)


@router.post("/webhooks/linear/{connection_id}", response_model=IssueSyncWebhookResponse)
async def ingest_linear_webhook(
    connection_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_webhook:linear")),
    linear_signature: str | None = Header(default=None, alias="Linear-Signature"),
) -> IssueSyncWebhookResponse:
    raw_body, payload = await _parse_webhook_body(request)
    row, is_duplicate = IssueSyncService(db).ingest_linear_webhook(
        org_id=organization.id,
        connection_id=connection_id,
        payload=payload,
        raw_body=raw_body,
        signature=linear_signature,
    )
    db.commit()
    detail = "duplicate linear webhook delivery ignored" if is_duplicate else "linear webhook processed"
    return IssueSyncWebhookResponse(processed=True, event_id=row.id, status=row.status, detail=detail, duplicate_delivery=is_duplicate)


@router.get("/connections/{connection_id}/events", response_model=list[IssueSyncEventRead])
def list_events(
    connection_id: uuid.UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_events:list")),
) -> list[IssueSyncEventRead]:
    rows = IssueSyncService(db).list_events(organization.id, connection_id, min(max(limit, 1), 500))
    return [_event_read(row) for row in rows]


@router.get("/issues/{issue_id}/comments", response_model=list[IssueSyncCommentRead])
def list_issue_comments(
    issue_id: uuid.UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issue_sync_comments:list")),
) -> list[IssueSyncCommentRead]:
    rows = IssueSyncService(db).list_issue_comments(organization.id, issue_id, min(max(limit, 1), 500))
    return [_comment_read(row) for row in rows]
