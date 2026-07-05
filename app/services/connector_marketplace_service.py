import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select, update
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
        schema_changed = "config_schema" in updates and updates["config_schema"] != row.config_schema
        for key, value in updates.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()
        if schema_changed:
            # The connector's config contract changed -- every org's previously-validated
            # enablement may no longer satisfy it, so force re-validation via test-connection.
            self.db.execute(
                update(ConnectorOrgEnablement)
                .where(ConnectorOrgEnablement.connector_id == connector_id, ConnectorOrgEnablement.enabled.is_(True))
                .values(connection_status="unconfigured", connection_error="Connector schema changed; re-validate configuration")
            )
        AuditService(self.db).write_audit_log(
            action="connector.catalog_updated",
            entity_type="connector_catalog_entry",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json=self._entry_snapshot(row),
            metadata_json={"source": "api", "schema_changed": schema_changed},
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

    @staticmethod
    def _validate_config_values(config_schema: dict | None, config_values: dict | None) -> list[str]:
        """Validate config_values against the connector's declared config_schema.

        This is a structural check only (required fields present, primitive types match) --
        it does NOT perform a live network call to the third-party system. Callers must treat
        a passing result as "configuration looks complete", not "we successfully connected".
        """
        errors: list[str] = []
        schema = config_schema or {}
        values = config_values or {}
        required = schema.get("required") or []
        properties = schema.get("properties") or {}
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "object": dict,
            "boolean": bool,
            "number": (int, float),
            "integer": int,
            "array": list,
        }
        for field in required:
            value = values.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                errors.append(f"Missing required field: {field}")
        for field, value in values.items():
            spec = properties.get(field)
            if not spec or value is None:
                continue
            expected = type_map.get(spec.get("type"))
            if expected and not isinstance(value, expected):
                errors.append(f"Field '{field}' must be of type {spec.get('type')}")
        return errors

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

        # Preserve previously-stored config when merely toggling enabled state without resending
        # config_values_json -- otherwise a disable/enable cycle silently wipes stored credentials.
        effective_config = config_values_json
        if config_values_json is None and row is not None:
            effective_config = row.config_values_json

        checked_at = self.utcnow()
        if enabled:
            errors = self._validate_config_values(connector.config_schema, effective_config)
            if errors:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"message": "Connector configuration is invalid", "errors": errors},
                )
            connection_status = "validated"
            connection_error = None
        else:
            connection_status = "disconnected"
            connection_error = None

        before = None
        if row is None:
            row = ConnectorOrgEnablement(
                organization_id=org_id,
                connector_id=connector_id,
                enabled=enabled,
                config_values_json=effective_config,
                connection_status=connection_status,
                connection_checked_at=checked_at,
                connection_error=connection_error,
                updated_by_user_id=user_id,
                updated_at=checked_at,
            )
            self.db.add(row)
        else:
            before = {
                "enabled": row.enabled,
                "config_values_json": row.config_values_json,
                "connection_status": row.connection_status,
            }
            row.enabled = enabled
            row.config_values_json = effective_config
            row.connection_status = connection_status
            row.connection_checked_at = checked_at
            row.connection_error = connection_error
            row.updated_by_user_id = user_id
            row.updated_at = checked_at
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
                "connection_status": row.connection_status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def test_connection(self, org_id: uuid.UUID, connector_id: uuid.UUID, user_id: uuid.UUID) -> ConnectorOrgEnablement:
        """Re-validate a configured connector's stored config against its schema.

        Labeled explicitly: this checks configuration completeness/shape only. It cannot and does
        not reach out to the real third-party system (no outbound credentials exist for
        Salesforce/Workday/ServiceNow/etc. in this environment).
        """
        connector = self._require_entry(connector_id)
        row = self.db.execute(
            select(ConnectorOrgEnablement).where(
                ConnectorOrgEnablement.organization_id == org_id,
                ConnectorOrgEnablement.connector_id == connector_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector is not enabled for this organization")

        before = {"connection_status": row.connection_status, "connection_error": row.connection_error}
        errors = self._validate_config_values(connector.config_schema, row.config_values_json)
        row.connection_checked_at = self.utcnow()
        if not row.enabled:
            row.connection_status = "disconnected"
            row.connection_error = None
        elif errors:
            row.connection_status = "invalid"
            row.connection_error = "; ".join(errors)
        else:
            row.connection_status = "validated"
            row.connection_error = None
        row.updated_at = row.connection_checked_at
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="connector.connection_tested",
            entity_type="connector_org_enablement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={"connection_status": row.connection_status, "connection_error": row.connection_error},
            metadata_json={"source": "api", "validation_mode": "schema_only"},
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
