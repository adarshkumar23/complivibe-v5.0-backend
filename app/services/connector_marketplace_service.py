import uuid
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.url_security import UnsafeURLTargetError, assert_public_http_url
from app.models.connector_catalog_entry import ConnectorCatalogEntry, ConnectorOrgEnablement
from app.services.audit_service import AuditService
from app.services.secrets_service import SecretsService

# Field names (case-insensitive substring match) that hold credentials and must be encrypted
# at rest via the vault transit backend rather than stored as plaintext in config_values_json.
_SENSITIVE_FIELD_MARKERS = ("token", "secret", "password", "credential", "apikey", "api_key", "key")
# Field names that hold the connector's network target -- used to pick what to actually probe
# during test-connection. Every real connector in the seed catalog uses one of these.
_URL_FIELD_MARKERS = ("url", "endpoint", "host")
_CONNECTION_TIMEOUT_SECONDS = 5.0


class ConnectorMarketplaceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _secrets(self, organization_id: uuid.UUID) -> SecretsService:
        return SecretsService(self.db, organization_id=organization_id)

    @staticmethod
    def sensitive_field_names(config_schema: dict | None) -> set[str]:
        properties = (config_schema or {}).get("properties") or {}
        return {name for name in properties if any(marker in name.lower() for marker in _SENSITIVE_FIELD_MARKERS)}

    @staticmethod
    def _url_field_names(config_schema: dict | None) -> list[str]:
        properties = (config_schema or {}).get("properties") or {}
        required = set((config_schema or {}).get("required") or [])
        names = [name for name in properties if any(marker in name.lower() for marker in _URL_FIELD_MARKERS)]
        # Prefer a required URL-shaped field -- every seeded connector's network target is required.
        names.sort(key=lambda name: (name not in required, name))
        return names

    def _encrypt_sensitive_fields(
        self,
        config_schema: dict | None,
        config_values: dict | None,
        *,
        org_id: uuid.UUID,
        entity_id: uuid.UUID | None,
    ) -> dict | None:
        """Encrypt any credential-shaped fields in `config_values` before it's persisted.

        Idempotent: a value that's already vault-ciphertext (e.g. carried over from a prior
        save) is left untouched rather than double-encrypted.
        """
        if not config_values:
            return config_values
        sensitive = self.sensitive_field_names(config_schema)
        if not sensitive:
            return dict(config_values)
        secrets = self._secrets(org_id)
        encrypted = dict(config_values)
        for field in sensitive:
            value = encrypted.get(field)
            if isinstance(value, str) and value and not SecretsService.is_vault_format(value):
                encrypted[field] = secrets.encrypt(value, secret_name="connector_config_value", entity_id=entity_id)
        return encrypted

    def _decrypt_sensitive_fields(
        self,
        config_schema: dict | None,
        config_values: dict | None,
        *,
        org_id: uuid.UUID,
        entity_id: uuid.UUID | None,
    ) -> dict | None:
        """Decrypt credential-shaped fields for actual use (e.g. a live test-connection call).

        Values that aren't vault-ciphertext (rows written before this encryption was added) are
        passed through unchanged rather than raising -- they're legacy plaintext, not corrupt.
        """
        if not config_values:
            return config_values
        sensitive = self.sensitive_field_names(config_schema)
        if not sensitive:
            return dict(config_values)
        secrets = self._secrets(org_id)
        decrypted = dict(config_values)
        for field in sensitive:
            value = decrypted.get(field)
            if isinstance(value, str) and value and SecretsService.is_vault_format(value):
                decrypted[field] = secrets.decrypt(value, secret_name="connector_config_value", entity_id=entity_id)
        return decrypted

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

        This is a structural check only (required fields present, primitive types match). Passing
        this check means "configuration looks complete" -- whether the target is actually reachable
        is verified separately by test_connection's live HTTP probe.
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
        # Schema validation always runs against the plaintext the caller supplied this call, or
        # (when reusing a prior config) the already-persisted value; encrypting a sensitive field
        # never changes whether it's present or a string, so validating post-encryption would give
        # the same answer -- but validating pre-encryption avoids ever running validation logic
        # against ciphertext unnecessarily.
        incoming_plaintext = config_values_json
        if incoming_plaintext is not None:
            validation_config = incoming_plaintext
            effective_config = self._encrypt_sensitive_fields(
                connector.config_schema, incoming_plaintext, org_id=org_id, entity_id=row.id if row is not None else None
            )
        else:
            validation_config = row.config_values_json if row is not None else None
            effective_config = validation_config

        checked_at = self.utcnow()
        if enabled:
            errors = self._validate_config_values(connector.config_schema, validation_config)
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
                # config_values_json here already has any credential fields encrypted --
                # the audit trail never contains plaintext secrets.
                "config_values_json": row.config_values_json,
                "connection_status": row.connection_status,
            },
            metadata_json={"source": "api"},
        )
        return row

    @classmethod
    def _extract_target_url(cls, config_schema: dict | None, config_values: dict | None) -> str | None:
        if not config_values:
            return None
        for field in cls._url_field_names(config_schema):
            value = config_values.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @classmethod
    def _probe_connection(cls, url: str, config_values: dict | None) -> tuple[bool, str | None]:
        """Perform a real outbound HTTP request to `url` with a short timeout.

        Returns (reachable, error_detail). Any DNS failure, connection refusal, or timeout is
        caught and reported honestly as unreachable rather than swallowed -- a genuinely fake or
        offline endpoint must fail this check.

        This request carries the connector's DECRYPTED credential as a bearer token to a
        tenant-supplied URL, so the target must be proven public first. Without that, a tenant
        could point base_url at a host they control and harvest their org's real API key, or aim
        it at internal infrastructure (including 169.254.169.254) and use the reachable/unreachable
        verdict as a port scanner.
        """
        target = url if "://" in url else f"https://{url}"

        try:
            assert_public_http_url(target, field_name="connector target URL")
        except UnsafeURLTargetError as exc:
            return False, str(exc)

        headers: dict[str, str] = {}
        for field, value in (config_values or {}).items():
            if not isinstance(value, str) or not value:
                continue
            lowered = field.lower()
            if "token" in lowered or lowered == "jwt_token":
                headers["Authorization"] = f"Bearer {value}"
                break

        try:
            # follow_redirects=False deliberately: the pre-flight check above validates only the
            # URL we were given, so a 302 to an internal address would walk the credential straight
            # past it. A redirecting endpoint reports as reachable, which is true and harmless.
            with httpx.Client(timeout=_CONNECTION_TIMEOUT_SECONDS, follow_redirects=False) as http_client:
                http_client.get(target, headers=headers)
            return True, None
        except httpx.RequestError as exc:
            # Class name only -- the full exception text carries resolved addresses and errno
            # detail, which turns an honest "unreachable" into a network-reconnaissance oracle.
            return False, exc.__class__.__name__
        except Exception as exc:  # e.g. an unparsable/unsupported URL -- report, don't crash
            return False, exc.__class__.__name__

    def test_connection(self, org_id: uuid.UUID, connector_id: uuid.UUID, user_id: uuid.UUID) -> ConnectorOrgEnablement:
        """Re-validate a configured connector: schema/shape check, then -- when the connector's
        config_schema declares a network-target field (base_url/instance_url/org_url/etc.) -- a
        genuine outbound HTTP request to it with a bounded timeout. A schema-only pass no longer
        implies "connected": an unreachable or fake target is reported as such. Connectors with no
        network endpoint in their schema (e.g. file-based ingest) fall back to schema-only
        validation, labeled accordingly in the audit trail's validation_mode.
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
        plaintext_config = self._decrypt_sensitive_fields(
            connector.config_schema, row.config_values_json, org_id=org_id, entity_id=row.id
        )
        errors = self._validate_config_values(connector.config_schema, plaintext_config)
        row.connection_checked_at = self.utcnow()

        validation_mode = "schema_only"
        if not row.enabled:
            row.connection_status = "disconnected"
            row.connection_error = None
        elif errors:
            row.connection_status = "invalid"
            row.connection_error = "; ".join(errors)
        else:
            target_url = self._extract_target_url(connector.config_schema, plaintext_config)
            if target_url is None:
                row.connection_status = "validated"
                row.connection_error = None
            else:
                validation_mode = "live_http"
                reachable, detail = self._probe_connection(target_url, plaintext_config)
                if reachable:
                    row.connection_status = "validated"
                    row.connection_error = None
                else:
                    row.connection_status = "unreachable"
                    row.connection_error = detail

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
            metadata_json={"source": "api", "validation_mode": validation_mode},
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
