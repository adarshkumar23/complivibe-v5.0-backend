import uuid

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.lineage import (
    LineageEdgeCreate,
    LineageEdgeRead,
    LineageGraphRead,
    LineageNodeCreate,
    LineageNodeRead,
    OpenLineageEventResult,
    OpenMetadataConfigureRead,
    OpenMetadataConfigureRequest,
    OpenMetadataStatusRead,
    OpenMetadataSyncRead,
)
from app.data_observability.services.lineage_service import LineageService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/lineage", tags=["data-observability-lineage"])


def _node_read(service: LineageService, organization_id: uuid.UUID, row) -> LineageNodeRead:
    return LineageNodeRead.model_validate(service.node_response_payload(organization_id, row))


@router.post("/nodes", response_model=LineageNodeRead, status_code=status.HTTP_201_CREATED)
def create_lineage_node(
    payload: LineageNodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> LineageNodeRead:
    service = LineageService(db)
    row = service.create_node(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _node_read(service, organization.id, row)


@router.get("/nodes", response_model=list[LineageNodeRead])
def list_lineage_nodes(
    node_type: str | None = Query(default=None),
    data_asset_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[LineageNodeRead]:
    service = LineageService(db)
    rows = service.list_nodes(organization.id, node_type=node_type, data_asset_id=data_asset_id)
    return [_node_read(service, organization.id, row) for row in rows]


@router.post("/nodes/{node_id}/link-asset/{asset_id}", response_model=LineageNodeRead)
def link_asset_to_lineage_node(
    node_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> LineageNodeRead:
    service = LineageService(db)
    row = service.link_asset_to_node(organization.id, asset_id, node_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _node_read(service, organization.id, row)


@router.post("/edges", response_model=LineageEdgeRead, status_code=status.HTTP_201_CREATED)
def create_lineage_edge(
    payload: LineageEdgeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> LineageEdgeRead:
    row = LineageService(db).create_edge(
        organization.id,
        payload.upstream_node_id,
        payload.downstream_node_id,
        payload,
        source_method="manual",
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return LineageEdgeRead.model_validate(row)


@router.get("/assets/{asset_id}/lineage", response_model=LineageGraphRead)
def get_asset_lineage_graph(
    asset_id: uuid.UUID,
    depth: int = Query(default=3, ge=1, le=5),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> LineageGraphRead:
    payload = LineageService(db).get_lineage_graph(organization.id, asset_id, depth=depth)
    return LineageGraphRead.model_validate(payload)


@router.post("/events", response_model=OpenLineageEventResult, status_code=status.HTTP_201_CREATED)
def receive_openlineage_event(
    event_payload: dict = Body(...),
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> OpenLineageEventResult:
    service = LineageService(db)
    org_id = service.resolve_org_by_api_key(x_complivibe_key or "")
    result = service.process_openlineage_event(org_id=org_id, event=event_payload, actor_user_id=None)
    db.commit()
    return OpenLineageEventResult.model_validate(result)


@router.post("/openmetadata/configure", response_model=OpenMetadataConfigureRead)
def configure_openmetadata(
    payload: OpenMetadataConfigureRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> OpenMetadataConfigureRead:
    row, ingest_key = LineageService(db).configure_openmetadata(
        org_id=organization.id,
        base_url=payload.base_url,
        jwt_token=payload.jwt_token,
        created_by=current_user.id,
        org_api_key=payload.org_api_key,
    )
    db.commit()
    db.refresh(row)
    return OpenMetadataConfigureRead(
        id=row.id,
        organization_id=row.organization_id,
        base_url=row.base_url,
        sync_status=row.sync_status,
        last_synced_at=row.last_synced_at,
        last_sync_error=row.last_sync_error,
        is_active=row.is_active,
        api_key_configured=True,
        ingest_api_key=ingest_key,
    )


@router.post("/openmetadata/sync", response_model=OpenMetadataSyncRead)
def sync_openmetadata(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> OpenMetadataSyncRead:
    payload = LineageService(db).sync_openmetadata(org_id=organization.id, triggered_by=current_user.id)
    db.commit()
    return OpenMetadataSyncRead.model_validate(payload)


@router.get("/openmetadata/status", response_model=OpenMetadataStatusRead)
def get_openmetadata_status(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> OpenMetadataStatusRead:
    row = LineageService(db).get_openmetadata_status(organization.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenMetadata integration not found")
    return OpenMetadataStatusRead(
        id=row.id,
        organization_id=row.organization_id,
        base_url=row.base_url,
        sync_status=row.sync_status,
        last_synced_at=row.last_synced_at,
        last_sync_error=row.last_sync_error,
        is_active=row.is_active,
        api_key_configured=True,
    )
