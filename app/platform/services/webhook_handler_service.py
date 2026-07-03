from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
try:
    import sentry_sdk
except Exception:  # pragma: no cover - optional in local test environments
    sentry_sdk = None  # type: ignore[assignment]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing_event import BillingEvent
from app.models.organization import Organization
from app.models.subscription_plan import SubscriptionPlan
from app.platform.services.razorpay_service import RazorpayService
from app.services.audit_service import AuditService


class WebhookHandlerService:
    def __init__(self, db: Session):
        self.db = db
        self.rzp = RazorpayService()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _capture_exception(exc: Exception) -> None:
        settings = get_settings()
        if settings.SENTRY_DSN and sentry_sdk is not None:
            sentry_sdk.capture_exception(exc)

    def handle(self, payload: dict, razorpay_event_id: str | None) -> dict:
        if razorpay_event_id:
            existing = self.db.execute(
                select(BillingEvent).where(BillingEvent.razorpay_event_id == razorpay_event_id)
            ).scalar_one_or_none()
            if existing:
                return {"status": "already_processed"}

        entity = payload.get("payload", {})
        sub_id = entity.get("subscription", {}).get("entity", {}).get("id")
        if not sub_id:
            return {"status": "org_not_found"}

        org = self.db.execute(
            select(Organization).where(Organization.razorpay_subscription_id == sub_id)
        ).scalar_one_or_none()
        if not org:
            return {"status": "org_not_found"}

        event_type = str(payload.get("event") or "unknown")
        billing_event = BillingEvent(
            organization_id=org.id,
            event_type=event_type,
            razorpay_event_id=razorpay_event_id,
            payload=payload,
        )
        self.db.add(billing_event)
        self.db.flush()

        handlers = {
            "subscription.activated": self._on_activated,
            "subscription.charged": self._on_charged,
            "subscription.halted": self._on_halted,
            "subscription.cancelled": self._on_cancelled,
            "subscription.paused": self._on_paused,
            "subscription.resumed": self._on_resumed,
            "subscription.completed": self._on_completed,
            "subscription.pending": self._on_pending,
            "payment.failed": self._on_payment_failed,
            "payment.captured": self._on_payment_captured,
            "invoice.paid": self._on_invoice_paid,
            "invoice.expired": self._on_invoice_expired,
            "refund.processed": self._on_refund_processed,
            "refund.failed": self._on_refund_failed,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                handler(org, payload)
                billing_event.processed = True
                billing_event.processed_at = self.utcnow()
            except Exception as exc:
                self._capture_exception(exc)
                billing_event.error_message = str(exc)
        else:
            billing_event.processed = True
            billing_event.processed_at = self.utcnow()

        self.db.flush()
        return {"status": "processed"}

    def _on_activated(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "active"
        plan_id = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("plan_id")
        if plan_id:
            plan = self.db.execute(
                select(SubscriptionPlan).where(
                    sa.or_(
                        SubscriptionPlan.razorpay_plan_id == plan_id,
                        SubscriptionPlan.razorpay_annual_plan_id == plan_id,
                    )
                )
            ).scalar_one_or_none()
            if plan:
                org.subscription_plan = plan.plan_code
        self._write_audit(org, "billing.subscription_activated")

    def _on_charged(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "active"
        charge_at = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("charge_at")
        if charge_at:
            org.subscription_ends_at = datetime.fromtimestamp(charge_at, tz=UTC)
        self._write_audit(org, "billing.payment_charged")

    def _on_halted(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "past_due"
        self._write_audit(org, "billing.subscription_halted")

    def _on_cancelled(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "cancelled"
        self._write_audit(org, "billing.subscription_cancelled")

    def _on_paused(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "paused"
        self._write_audit(org, "billing.subscription_paused")

    def _on_resumed(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "active"
        self._write_audit(org, "billing.subscription_resumed")

    def _on_completed(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "expired"
        self._write_audit(org, "billing.subscription_completed")

    def _on_pending(self, org: Organization, payload: dict) -> None:
        org.subscription_status = "past_due"
        self._write_audit(org, "billing.payment_pending")

    def _on_payment_failed(self, org: Organization, payload: dict) -> None:
        self._write_audit(org, "billing.payment_failed")

    def _on_payment_captured(self, org: Organization, payload: dict) -> None:
        self._write_audit(org, "billing.payment_captured")

    def _on_invoice_paid(self, org: Organization, payload: dict) -> None:
        self._write_audit(org, "billing.invoice_paid")

    def _on_invoice_expired(self, org: Organization, payload: dict) -> None:
        self._write_audit(org, "billing.invoice_expired")

    def _on_refund_processed(self, org: Organization, payload: dict) -> None:
        self._write_audit(org, "billing.refund_processed")

    def _on_refund_failed(self, org: Organization, payload: dict) -> None:
        self._write_audit(org, "billing.refund_failed")

    def _write_audit(self, org: Organization, action: str) -> None:
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type="organizations",
            organization_id=org.id,
            entity_id=org.id,
        )
