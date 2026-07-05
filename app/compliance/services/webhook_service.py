from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_endpoint import WebhookEndpoint
from app.services.audit_service import AuditService


class WebhookService:
    ALLOWED_EVENT_TYPES: tuple[str, ...] = (
        "control.failed",
        "risk.critical",
        "evidence.expired",
        "deadline.overdue",
        "issue.created",
        "alert.triggered",
    )

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def _validate_event_types(cls, event_types: list[str]) -> list[str]:
        unique = list(dict.fromkeys(event_types))
        unknown = [event for event in unique if event not in cls.ALLOWED_EVENT_TYPES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown webhook event types: {', '.join(sorted(unknown))}",
            )
        return unique

    def create_endpoint(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> WebhookEndpoint:
        event_types = self._validate_event_types(list(data.event_types or []))
        row = WebhookEndpoint(
            organization_id=org_id,
            url=data.url,
            name=data.name,
            secret=data.secret,
            event_types=event_types,
            is_active=True,
            created_by=created_by,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="webhook_endpoint.created",
            entity_type="webhook_endpoint",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"url": row.url, "event_types": list(row.event_types or []), "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def get_endpoint(self, org_id: uuid.UUID, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        row = self.db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.organization_id == org_id,
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found")
        return row

    def list_endpoints(self, org_id: uuid.UUID, *, is_active: bool | None = None) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == org_id,
            WebhookEndpoint.deleted_at.is_(None),
        )
        if is_active is not None:
            stmt = stmt.where(WebhookEndpoint.is_active.is_(is_active))
        return self.db.execute(stmt.order_by(WebhookEndpoint.created_at.desc())).scalars().all()

    def update_endpoint(self, org_id: uuid.UUID, endpoint_id: uuid.UUID, data, actor_user_id: uuid.UUID | None = None) -> WebhookEndpoint:
        row = self.get_endpoint(org_id, endpoint_id)
        updates = data.model_dump(exclude_unset=True)

        if "event_types" in updates and updates["event_types"] is not None:
            updates["event_types"] = self._validate_event_types(list(updates["event_types"]))

        before = {
            "url": row.url,
            "name": row.name,
            "event_types": list(row.event_types or []),
            "is_active": bool(row.is_active),
        }

        for field, value in updates.items():
            setattr(row, field, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="webhook_endpoint.updated",
            entity_type="webhook_endpoint",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "url": row.url,
                "name": row.name,
                "event_types": list(row.event_types or []),
                "is_active": bool(row.is_active),
            },
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_endpoint(self, org_id: uuid.UUID, endpoint_id: uuid.UUID, user_id: uuid.UUID) -> WebhookEndpoint:
        row = self.get_endpoint(org_id, endpoint_id)
        row.is_active = False
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="webhook_endpoint.deactivated",
            entity_type="webhook_endpoint",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": bool(row.is_active)},
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_endpoint(self, org_id: uuid.UUID, endpoint_id: uuid.UUID, user_id: uuid.UUID) -> WebhookEndpoint:
        row = self.get_endpoint(org_id, endpoint_id)
        if row.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only inactive webhook endpoints can be deleted")

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="webhook_endpoint.deleted",
            entity_type="webhook_endpoint",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None},
            metadata_json={"source": "api"},
        )
        return row

    @staticmethod
    def _payload_string(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, default=str)

    @classmethod
    def _payload_hash(cls, payload: dict) -> str:
        payload_str = cls._payload_string(payload)
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    @classmethod
    def _signature(cls, *, secret: str, payload: dict) -> str:
        payload_str = cls._payload_string(payload)
        sig = hmac.new(
            secret.encode("utf-8"),
            payload_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={sig}"

    def emit(self, org_id: uuid.UUID, event_type: str, payload: dict) -> list[WebhookDelivery]:
        if event_type not in self.ALLOWED_EVENT_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown webhook event type")

        endpoints = self.db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.organization_id == org_id,
                WebhookEndpoint.deleted_at.is_(None),
                WebhookEndpoint.is_active.is_(True),
            )
        ).scalars().all()

        deliveries: list[WebhookDelivery] = []
        payload_hash = self._payload_hash(payload)
        for endpoint in endpoints:
            if event_type not in list(endpoint.event_types or []):
                continue

            row = WebhookDelivery(
                organization_id=org_id,
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=dict(payload),
                payload_hash=payload_hash,
                signature=self._signature(secret=endpoint.secret, payload=payload),
                status="pending",
                attempts=0,
            )
            self.db.add(row)
            deliveries.append(row)

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="webhook.emitted",
            entity_type="webhook_delivery",
            organization_id=org_id,
            actor_user_id=None,
            after_json={"event_type": event_type, "deliveries_created": len(deliveries)},
            metadata_json={"source": "service"},
        )
        return deliveries

    def deliver(self, delivery_id: uuid.UUID) -> WebhookDelivery:
        row = self.db.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook delivery not found")

        endpoint = self.db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == row.endpoint_id,
                WebhookEndpoint.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        attempts = int(row.attempts or 0)

        if endpoint is None:
            row.attempts = attempts + 1
            row.last_attempted_at = self.utcnow()
            row.status = "failed"
            row.error_message = "Webhook endpoint not found or deleted"
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="webhook.delivery_failed",
                entity_type="webhook_delivery",
                entity_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=None,
                after_json={"status": "failed", "attempts": row.attempts, "error": row.error_message},
                metadata_json={"source": "webhook_service"},
            )
            return row

        payload = dict(row.payload or {})
        headers = {
            "Content-Type": "application/json",
            "X-CompliVibe-Payload-Hash": row.payload_hash,
            "X-CompliVibe-Signature": row.signature or "",
        }

        last_status: int | None = None
        last_error: str | None = None

        for attempt in range(3):
            row.attempts = attempts + attempt + 1
            row.last_attempted_at = self.utcnow()
            self.db.flush()

            try:
                response = httpx.post(
                    endpoint.url,
                    json=payload,
                    headers=headers,
                    timeout=httpx.Timeout(10.0, connect=10.0),
                )
                last_status = response.status_code
                response.raise_for_status()

                row.status = "delivered"
                row.delivered_at = self.utcnow()
                row.response_code = response.status_code
                row.error_message = None
                self.db.flush()

                AuditService(self.db).write_audit_log(
                    action="webhook.delivered",
                    entity_type="webhook_delivery",
                    entity_id=row.id,
                    organization_id=row.organization_id,
                    actor_user_id=None,
                    after_json={
                        "endpoint_id": str(endpoint.id),
                        "url": endpoint.url,
                        "response_code": response.status_code,
                        "attempts": row.attempts,
                    },
                    metadata_json={"source": "webhook_service"},
                )
                return row
            except httpx.HTTPStatusError as exc:
                last_status = exc.response.status_code
                last_error = f"HTTP {exc.response.status_code}"
            except Exception as exc:  # pragma: no cover - network/timeout errors
                last_error = str(exc) or type(exc).__name__

            if attempt < 2:
                # Exponential backoff: 1s, then 3s.
                time.sleep(1 if attempt == 0 else 3)

        row.status = "failed"
        row.response_code = last_status
        row.error_message = last_error or "Delivery failed after 3 attempts"
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="webhook.delivery_failed",
            entity_type="webhook_delivery",
            entity_id=row.id,
            organization_id=row.organization_id,
            actor_user_id=None,
            after_json={
                "endpoint_id": str(endpoint.id),
                "url": endpoint.url,
                "response_code": last_status,
                "attempts": row.attempts,
                "error": row.error_message,
            },
            metadata_json={"source": "webhook_service"},
        )
        return row

    def get_delivery(self, org_id: uuid.UUID, delivery_id: uuid.UUID) -> WebhookDelivery:
        row = self.db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook delivery not found")
        return row

    def get_deliveries(
        self,
        org_id: uuid.UUID,
        *,
        endpoint_id: uuid.UUID | None = None,
        status_value: str | None = None,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        stmt = select(WebhookDelivery).where(WebhookDelivery.organization_id == org_id)
        if endpoint_id is not None:
            _ = self.get_endpoint(org_id, endpoint_id)
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
        if status_value is not None:
            stmt = stmt.where(WebhookDelivery.status == status_value)
        return self.db.execute(stmt.order_by(WebhookDelivery.created_at.desc()).limit(limit)).scalars().all()

    @classmethod
    def list_event_types(cls) -> list[str]:
        return list(cls.ALLOWED_EVENT_TYPES)
