from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.url_security import UnsafeURLTargetError, assert_public_http_url, raise_unsafe_url_http_error
from app.models.audit_log import AuditLog
from app.models.siem_export_config import SiemExportConfig
from app.models.siem_export_run import SiemExportRun
from app.platform.schemas.siem import SiemConfigCreate, SiemConfigUpdate
from app.services.audit_service import AuditService

# Delivery methods that push over HTTP(S) and are actually implemented today. "webhook"
# is the only push transport wired up to real HTTP delivery; "syslog"/"file" are accepted
# by the schema/DB check constraint but have no delivery implementation, and "api_pull" is
# intentionally pull-only (the SIEM polls /siem/export).
PUSH_CAPABLE_DELIVERY_METHODS = {"webhook"}
UNIMPLEMENTED_PUSH_DELIVERY_METHODS = {"syslog", "file"}


class SiemExportService:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def create_config(
        self,
        org_id: uuid.UUID,
        data: SiemConfigCreate,
        created_by: uuid.UUID,
        db: Session,
    ) -> SiemExportConfig:
        existing = self._get_config(org_id, db)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SIEM config already exists. Update it.")

        self._validate_delivery_method(data.delivery_method, data.endpoint_url)

        api_key_hash = hashlib.sha256(data.api_key.encode()).hexdigest() if data.api_key else None
        config = SiemExportConfig(
            organization_id=org_id,
            export_format=data.export_format,
            delivery_method=data.delivery_method,
            endpoint_url=data.endpoint_url,
            api_key_hash=api_key_hash,
            include_actions=data.include_actions,
            exclude_actions=data.exclude_actions,
            batch_size=data.batch_size,
            created_by=created_by,
        )
        db.add(config)
        db.flush()

        AuditService(db).write_audit_log(
            action="siem_config.created",
            entity_type="siem_export_configs",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=config.id,
        )
        return config

    def get_config(self, org_id: uuid.UUID, db: Session) -> SiemExportConfig:
        config = self._get_config(org_id, db)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SIEM config not found")
        return config

    def update_config(
        self,
        org_id: uuid.UUID,
        data: SiemConfigUpdate,
        actor_user_id: uuid.UUID,
        db: Session,
    ) -> SiemExportConfig:
        config = self.get_config(org_id, db)
        payload = data.model_dump(exclude_unset=True)

        if "api_key" in payload:
            raw = payload.pop("api_key")
            config.api_key_hash = hashlib.sha256(raw.encode()).hexdigest() if raw else None

        effective_delivery_method = payload.get("delivery_method", config.delivery_method)
        effective_endpoint_url = payload.get("endpoint_url", config.endpoint_url)
        self._validate_delivery_method(effective_delivery_method, effective_endpoint_url)

        for field, value in payload.items():
            setattr(config, field, value)

        config.updated_at = self.utcnow()
        db.flush()

        AuditService(db).write_audit_log(
            action="siem_config.updated",
            entity_type="siem_export_configs",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            entity_id=config.id,
        )
        return config

    def activate_config(self, org_id: uuid.UUID, actor_user_id: uuid.UUID, db: Session) -> SiemExportConfig:
        config = self.get_config(org_id, db)
        config.is_active = True
        config.updated_at = self.utcnow()
        db.flush()
        AuditService(db).write_audit_log(
            action="siem_config.activated",
            entity_type="siem_export_configs",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            entity_id=config.id,
        )
        return config

    def deactivate_config(self, org_id: uuid.UUID, actor_user_id: uuid.UUID, db: Session) -> SiemExportConfig:
        config = self.get_config(org_id, db)
        config.is_active = False
        config.updated_at = self.utcnow()
        db.flush()
        AuditService(db).write_audit_log(
            action="siem_config.deactivated",
            entity_type="siem_export_configs",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            entity_id=config.id,
        )
        return config

    def delete_config(self, org_id: uuid.UUID, actor_user_id: uuid.UUID, db: Session) -> None:
        config = self.get_config(org_id, db)
        now = self.utcnow()
        config.is_active = False
        config.deleted_at = now
        config.updated_at = now
        db.flush()
        AuditService(db).write_audit_log(
            action="siem_config.deleted",
            entity_type="siem_export_configs",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            entity_id=config.id,
        )

    def export_batch(
        self,
        org_id: uuid.UUID,
        db: Session,
        limit: int | None = 100,
        since_id: uuid.UUID | None = None,
    ) -> dict:
        config = self._get_config(org_id, db)
        if not config or not config.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SIEM export not configured or inactive")

        effective_limit = max(1, min(limit or config.batch_size, 10000))
        run = SiemExportRun(
            organization_id=org_id,
            config_id=config.id,
            status="running",
            cursor_start=since_id,
        )
        db.add(run)
        db.flush()

        query = db.query(AuditLog).filter(AuditLog.organization_id == org_id)
        if since_id:
            cursor_entry = db.get(AuditLog, since_id)
            if cursor_entry and cursor_entry.organization_id == org_id:
                query = query.filter(AuditLog.created_at > cursor_entry.created_at)

        if config.include_actions:
            query = query.filter(AuditLog.action.in_(config.include_actions))
        if config.exclude_actions:
            query = query.filter(AuditLog.action.notin_(config.exclude_actions))

        entries = query.order_by(AuditLog.created_at.asc()).limit(effective_limit).all()

        if not entries:
            run.status = "completed"
            run.records_exported = 0
            run.completed_at = self.utcnow()
            db.flush()
            return {
                "records": 0,
                "payload": None,
                "cursor": str(since_id) if since_id else None,
                "has_more": False,
                "format": config.export_format,
            }

        payload = self._format_payload(config.export_format, entries)
        last_id = entries[-1].id
        now = self.utcnow()

        # Push delivery runs on the same cadence/event source as pull: whenever a batch is
        # exported (this method), a "webhook"-configured org also gets it POSTed to its
        # endpoint_url. Previously delivery_method/endpoint_url were captured at config time
        # but nothing ever read them again -- every export was silently pull-only regardless
        # of what the org configured.
        push_error = self._deliver_push(config, payload)

        if push_error:
            run.status = "partial"
            run.error_message = push_error
            config.export_failures = (config.export_failures or 0) + 1
        else:
            run.status = "completed"

        run.records_exported = len(entries)
        run.completed_at = now
        run.cursor_end = last_id
        config.last_exported_at = now
        config.last_export_id = last_id
        db.flush()

        return {
            "records": len(entries),
            "payload": payload,
            "cursor": str(last_id),
            "has_more": len(entries) == effective_limit,
            "format": config.export_format,
            "push_delivered": config.delivery_method in PUSH_CAPABLE_DELIVERY_METHODS and push_error is None,
            "push_error": push_error,
        }

    def _validate_delivery_method(self, delivery_method: str, endpoint_url: str | None) -> None:
        if delivery_method in PUSH_CAPABLE_DELIVERY_METHODS:
            if not endpoint_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"endpoint_url is required when delivery_method is '{delivery_method}'",
                )
            try:
                assert_public_http_url(endpoint_url, field_name="endpoint_url")
            except UnsafeURLTargetError as exc:
                raise_unsafe_url_http_error(exc, field_name="endpoint_url")
        elif delivery_method in UNIMPLEMENTED_PUSH_DELIVERY_METHODS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"delivery_method '{delivery_method}' is not yet implemented. "
                    "Supported delivery methods are 'webhook' (HTTP push) and 'api_pull' (poll /siem/export)."
                ),
            )
        # "api_pull" needs no endpoint_url and is always supported (it's the pull path).

    def _deliver_push(self, config: SiemExportConfig, payload: list[dict] | str) -> str | None:
        """POST the formatted export payload to config.endpoint_url. Returns an error
        string on failure, or None on success / when the config isn't push-configured."""
        if config.delivery_method not in PUSH_CAPABLE_DELIVERY_METHODS:
            return None
        if not config.endpoint_url:
            return "delivery_method is 'webhook' but no endpoint_url is configured"

        try:
            # Re-validate at delivery time (not just at config-save time) to guard against
            # DNS rebinding between when the endpoint was configured and when we deliver.
            assert_public_http_url(config.endpoint_url, field_name="endpoint_url")
        except UnsafeURLTargetError as exc:
            return str(exc)

        headers = {"X-CompliVibe-Export-Format": config.export_format}
        try:
            if isinstance(payload, str):
                headers["Content-Type"] = "text/plain"
                response = httpx.post(
                    config.endpoint_url,
                    content=payload,
                    headers=headers,
                    timeout=httpx.Timeout(15.0, connect=10.0),
                )
            else:
                headers["Content-Type"] = "application/json"
                response = httpx.post(
                    config.endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=httpx.Timeout(15.0, connect=10.0),
                )
            response.raise_for_status()
            return None
        except Exception as exc:  # pragma: no cover - network/timeout errors
            return str(exc) or type(exc).__name__

    def preview_export(self, org_id: uuid.UUID, db: Session) -> dict:
        config = self._get_config(org_id, db)
        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SIEM config not found")

        entries = (
            db.query(AuditLog)
            .filter(AuditLog.organization_id == org_id)
            .order_by(AuditLog.created_at.desc())
            .limit(10)
            .all()
        )
        ordered = list(reversed(entries))
        payload = self._format_payload(config.export_format, ordered)
        cursor = str(ordered[-1].id) if ordered else None
        return {
            "records": len(ordered),
            "payload": payload,
            "cursor": cursor,
            "has_more": False,
            "format": config.export_format,
        }

    def list_runs(self, org_id: uuid.UUID, db: Session, limit: int = 20) -> list[SiemExportRun]:
        return (
            db.query(SiemExportRun)
            .filter(SiemExportRun.organization_id == org_id)
            .order_by(SiemExportRun.started_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )

    def _format_payload(self, export_format: str, entries: list[AuditLog]) -> list[dict] | str:
        if export_format == "cef":
            return self._format_cef(entries)
        if export_format == "splunk_hec":
            return self._format_splunk_hec(entries)
        return self._format_json(entries)

    def _format_json(self, entries: list[AuditLog]) -> list[dict]:
        return [
            {
                "timestamp": item.created_at.isoformat(),
                "action": item.action,
                "entity_type": item.entity_type,
                "entity_id": str(item.entity_id) if item.entity_id else None,
                "organization_id": str(item.organization_id),
                "actor_user_id": str(item.actor_user_id) if item.actor_user_id else None,
                "ip_address": item.ip_address,
                "metadata": item.metadata_json or {},
            }
            for item in entries
        ]

    def _format_cef(self, entries: list[AuditLog]) -> str:
        lines: list[str] = []
        for item in entries:
            severity = self._action_to_cef_severity(item.action)
            ext_parts = [
                f"rt={int(item.created_at.timestamp() * 1000)}",
                f"suser={item.actor_user_id or 'system'}",
                "dvc=complivibe",
                f"cs1={item.organization_id}",
                "cs1Label=organizationId",
                f"cs2={item.entity_type}",
                "cs2Label=entityType",
            ]
            if item.ip_address:
                ext_parts.append(f"src={item.ip_address}")
            lines.append(
                f"CEF:0|CompliVibe|CompliVibe|5.0|{item.action}|{item.action}|{severity}|{' '.join(ext_parts)}"
            )
        return "\n".join(lines)

    def _format_splunk_hec(self, entries: list[AuditLog]) -> list[dict]:
        return [
            {
                "time": item.created_at.timestamp(),
                "host": "complivibe",
                "source": "complivibe:audit",
                "sourcetype": "complivibe:audit",
                "index": "compliance",
                "event": {
                    "action": item.action,
                    "entity_type": item.entity_type,
                    "entity_id": str(item.entity_id) if item.entity_id else None,
                    "org_id": str(item.organization_id),
                    "actor": str(item.actor_user_id) if item.actor_user_id else None,
                    "ip": item.ip_address,
                    "metadata": item.metadata_json or {},
                },
            }
            for item in entries
        ]

    def _action_to_cef_severity(self, action: str) -> int:
        high_signals = {
            "user.deprovisioned_via_scim",
            "sso.login",
            "breach_notification",
            "security.trivy_scan_ingested",
        }
        if any(signal in action for signal in high_signals):
            return 7
        if "delete" in action or "remove" in action:
            return 5
        if "create" in action or "update" in action:
            return 3
        return 1

    def _get_config(self, org_id: uuid.UUID, db: Session) -> SiemExportConfig | None:
        return db.execute(
            select(SiemExportConfig).where(
                SiemExportConfig.organization_id == org_id,
                SiemExportConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
