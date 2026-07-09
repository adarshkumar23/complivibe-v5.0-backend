import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.connector_catalog_entry import ConnectorCatalogEntry, ConnectorOrgEnablement
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.connector_marketplace import (
    ConnectorCatalogCreate,
    ConnectorCatalogRead,
    ConnectorCatalogUpdate,
    ConnectorEnableRequest,
    ConnectorOrgEnablementRead,
)
from app.services.connector_marketplace_service import ConnectorMarketplaceService
from app.services.seed_service import SeedService

router = APIRouter(prefix="/connectors", tags=["connector-marketplace"])


def _catalog_read(row: ConnectorCatalogEntry) -> ConnectorCatalogRead:
    return ConnectorCatalogRead.model_validate(row)


def _redact_sensitive_config(connector: ConnectorCatalogEntry, config_values: dict | None) -> dict | None:
    """Never echo credential values back through the API -- config_values_json for
    token/secret/password/key-shaped fields is encrypted at rest; API responses show a
    fixed redaction marker for those fields instead of the ciphertext."""
    if not config_values:
        return config_values
    sensitive = ConnectorMarketplaceService.sensitive_field_names(connector.config_schema)
    if not sensitive:
        return config_values
    redacted = dict(config_values)
    for field in sensitive:
        if redacted.get(field):
            redacted[field] = "••••••••"
    return redacted


def _enablement_read(row: ConnectorOrgEnablement, connector: ConnectorCatalogEntry) -> ConnectorOrgEnablementRead:
    return ConnectorOrgEnablementRead(
        id=row.id,
        organization_id=row.organization_id,
        connector_id=row.connector_id,
        enabled=row.enabled,
        config_values_json=_redact_sensitive_config(connector, row.config_values_json),
        connection_status=row.connection_status,
        connection_checked_at=row.connection_checked_at,
        connection_error=row.connection_error,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        connector=_catalog_read(connector),
    )


@router.get("/catalog", response_model=list[ConnectorCatalogRead])
def list_connectors(
    category: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("connectors:read")),
) -> list[ConnectorCatalogRead]:
    SeedService.ensure_connector_catalog(db)
    db.commit()
    rows = ConnectorMarketplaceService(db).list_catalog(category=category, enabled=enabled)
    return [_catalog_read(row) for row in rows]


@router.post("/catalog", response_model=ConnectorCatalogRead, status_code=status.HTTP_201_CREATED)
def create_connector(
    payload: ConnectorCatalogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorCatalogRead:
    row = ConnectorMarketplaceService(db).create_catalog_entry(payload, current_user.id, organization.id)
    db.commit()
    db.refresh(row)
    return _catalog_read(row)


@router.get("/catalog/{connector_id}", response_model=ConnectorCatalogRead)
def get_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorCatalogRead:
    row = ConnectorMarketplaceService(db)._require_entry(connector_id)
    return _catalog_read(row)


@router.patch("/catalog/{connector_id}", response_model=ConnectorCatalogRead)
def update_connector(
    connector_id: uuid.UUID,
    payload: ConnectorCatalogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorCatalogRead:
    row = ConnectorMarketplaceService(db).update_catalog_entry(connector_id, payload, current_user.id, organization.id)
    db.commit()
    db.refresh(row)
    return _catalog_read(row)


@router.delete("/catalog/{connector_id}", response_model=ConnectorCatalogRead)
def delete_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorCatalogRead:
    row = ConnectorMarketplaceService(db).soft_delete_catalog_entry(connector_id, current_user.id, organization.id)
    db.commit()
    db.refresh(row)
    return _catalog_read(row)


@router.get("/enabled", response_model=list[ConnectorOrgEnablementRead])
def list_enabled_connectors(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> list[ConnectorOrgEnablementRead]:
    rows = ConnectorMarketplaceService(db).list_org_enablements(organization.id)
    return [_enablement_read(row, connector) for row, connector in rows]


@router.post("/{connector_id}/enable", response_model=ConnectorOrgEnablementRead)
def enable_connector(
    connector_id: uuid.UUID,
    payload: ConnectorEnableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorOrgEnablementRead:
    service = ConnectorMarketplaceService(db)
    row = service.set_org_enablement(
        organization.id,
        connector_id,
        enabled=True,
        config_values_json=payload.config_values_json,
        user_id=current_user.id,
    )
    connector = service._require_entry(connector_id)
    db.commit()
    db.refresh(row)
    return _enablement_read(row, connector)


@router.post("/{connector_id}/disable", response_model=ConnectorOrgEnablementRead)
def disable_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorOrgEnablementRead:
    service = ConnectorMarketplaceService(db)
    row = service.set_org_enablement(organization.id, connector_id, enabled=False, config_values_json=None, user_id=current_user.id)
    connector = service._require_entry(connector_id)
    db.commit()
    db.refresh(row)
    return _enablement_read(row, connector)


@router.post("/{connector_id}/test-connection", response_model=ConnectorOrgEnablementRead)
def test_connector_connection(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorOrgEnablementRead:
    """Re-validate the organization's stored config for this connector.

    Checks configuration completeness/shape first, then -- when the connector's config_schema
    declares a network-target field (base_url/instance_url/org_url/etc.) -- performs a genuine
    outbound HTTP request to that target with a bounded timeout, reporting connection failures
    (DNS, refused, timeout) honestly rather than always returning "validated".
    """
    service = ConnectorMarketplaceService(db)
    row = service.test_connection(organization.id, connector_id, current_user.id)
    connector = service._require_entry(connector_id)
    db.commit()
    db.refresh(row)
    return _enablement_read(row, connector)
