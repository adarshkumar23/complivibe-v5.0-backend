import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.connector_catalog_entry import ConnectorCatalogEntry, ConnectorOrgEnablement
from app.services.audit_service import AuditService


class ConnectorMarketplaceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _entry_snapshot(row: ConnectorCatalogEntry) -> dict:
        return {
            "name": row.name,
            "category": row.category,
            "description": row.description,
            "config_schema": row.config_schema,
            "enabled": row.enabled,
            "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        }

    def _require_entry(self, connector_id: uuid.UUID, *, include_deleted: bool = False) -> ConnectorCatalogEntry:
        stmt = select(ConnectorCatalogEntry).where(ConnectorCatalogEntry.id == connector_id)
        if not include_deleted:
            stmt = stmt.where(ConnectorCatalogEntry.deleted_at.is_(None))
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
        return row

    def list_catalog(self, *, category: str | None = None, enabled: bool | None = None) -> list[ConnectorCatalogEntry]:
        stmt = select(ConnectorCatalogEntry).where(ConnectorCatalogEntry.deleted_at.is_(None))
        if category is not None:
            stmt = stmt.where(ConnectorCatalogEntry.category == category)
        if enabled is not None:
            stmt = stmt.where(ConnectorCatalogEntry.enabled.is_(enabled))
        return self.db.execute(stmt.order_by(ConnectorCatalogEntry.category.asc(), ConnectorCatalogEntry.name.asc())).scalars().all()

    def create_catalog_entry(self, payload, user_id: uuid.UUID, org_id: uuid.UUID) -> ConnectorCatalogEntry:
        duplicate = self.db.execute(
            select(ConnectorCatalogEntry.id).where(
                ConnectorCatalogEntry.name == payload.name,
                ConnectorCatalogEntry.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Connector name already exists")
        row = ConnectorCatalogEntry(
            name=payload.name,
            category=payload.category,
            description=payload.description,
            config_schema=payload.config_schema,
            enabled=payload.enabled,
            created_by_user_id=user_id,
            updated_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="connector.catalog_created",
            entity_type="connector_catalog_entry",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json=self._entry_snapshot(row),
            metadata_json={"source": "api"},
        )
        return row

    def update_catalog_entry(self, connector_id: uuid.UUID, payload, user_id: uuid.UUID, org_id: uuid.UUID) -> ConnectorCatalogEntry:
        row = self._require_entry(connector_id)
        before = self._entry_snapshot(row)
        updates = payload.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="connector.catalog_updated",
            entity_type="connector_catalog_entry",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json=self._entry_snapshot(row),
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_catalog_entry(self, connector_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID) -> ConnectorCatalogEntry:
        row = self._require_entry(connector_id)
        before = self._entry_snapshot(row)
        row.enabled = False
        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="connector.catalog_deleted",
            entity_type="connector_catalog_entry",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json=self._entry_snapshot(row),
            metadata_json={"source": "api", "soft_delete": True},
        )
        return row

    def set_org_enablement(
        self,
        org_id: uuid.UUID,
        connector_id: uuid.UUID,
        *,
        enabled: bool,
        config_values_json: dict | None,
        user_id: uuid.UUID,
    ) -> ConnectorOrgEnablement:
        connector = self._require_entry(connector_id)
        if not connector.enabled and enabled:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Connector is disabled in the catalog")
        row = self.db.execute(
            select(ConnectorOrgEnablement).where(
                ConnectorOrgEnablement.organization_id == org_id,
                ConnectorOrgEnablement.connector_id == connector_id,
            )
        ).scalar_one_or_none()
        before = None
        if row is None:
            row = ConnectorOrgEnablement(
                organization_id=org_id,
                connector_id=connector_id,
                enabled=enabled,
                config_values_json=config_values_json,
                updated_by_user_id=user_id,
                updated_at=self.utcnow(),
            )
            self.db.add(row)
        else:
            before = {
                "enabled": row.enabled,
                "config_values_json": row.config_values_json,
            }
            row.enabled = enabled
            if config_values_json is not None or enabled:
                row.config_values_json = config_values_json
            row.updated_by_user_id = user_id
            row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="connector.enabled" if enabled else "connector.disabled",
            entity_type="connector_org_enablement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "connector_id": str(connector_id),
                "enabled": row.enabled,
                "config_values_json": row.config_values_json,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_org_enablements(self, org_id: uuid.UUID) -> list[tuple[ConnectorOrgEnablement, ConnectorCatalogEntry]]:
        return self.db.execute(
            select(ConnectorOrgEnablement, ConnectorCatalogEntry)
            .join(ConnectorCatalogEntry, ConnectorCatalogEntry.id == ConnectorOrgEnablement.connector_id)
            .where(
                ConnectorOrgEnablement.organization_id == org_id,
                ConnectorOrgEnablement.enabled.is_(True),
                ConnectorCatalogEntry.deleted_at.is_(None),
            )
            .order_by(ConnectorCatalogEntry.name.asc())
        ).all()
