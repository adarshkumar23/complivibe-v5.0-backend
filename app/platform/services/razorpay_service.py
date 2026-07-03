from __future__ import annotations

import hashlib
import hmac
import uuid

import razorpay

from app.core.config import get_settings


class RazorpayService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    def verify_webhook_signature(self, payload_body: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return False
        expected = hmac.new(self.webhook_secret.encode(), payload_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def create_customer(self, org_id: uuid.UUID, org_name: str, admin_email: str, admin_name: str) -> str:
        customer = self.client.customer.create(
            {
                "name": admin_name,
                "email": admin_email,
                "fail_existing": "0",
                "notes": {
                    "org_id": str(org_id),
                    "org_name": org_name,
                    "platform": "complivibe",
                },
            }
        )
        return customer["id"]

    def create_subscription(
        self,
        razorpay_customer_id: str,
        razorpay_plan_id: str,
        org_id: uuid.UUID,
        quantity: int = 1,
        total_count: int = 120,
    ) -> dict:
        return self.client.subscription.create(
            {
                "plan_id": razorpay_plan_id,
                "customer_id": razorpay_customer_id,
                "quantity": quantity,
                "total_count": total_count,
                "notify_info": {
                    "notify_email": 1,
                    "notify_sms": 0,
                    "notify_whatsapp": 0,
                },
                "notes": {
                    "org_id": str(org_id),
                    "platform": "complivibe",
                },
            }
        )

    def cancel_subscription(self, razorpay_subscription_id: str, cancel_at_cycle_end: bool = True) -> dict:
        return self.client.subscription.cancel(
            razorpay_subscription_id,
            {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0},
        )

    def get_subscription(self, razorpay_subscription_id: str) -> dict:
        return self.client.subscription.fetch(razorpay_subscription_id)

    def get_invoices(self, razorpay_subscription_id: str) -> list:
        try:
            invoices = self.client.invoice.all({"subscription_id": razorpay_subscription_id, "count": 24})
            return invoices.get("items", [])
        except Exception:
            return []

    def create_razorpay_plan(self, plan_name: str, amount_paise: int, interval: str = "monthly") -> str:
        period = "monthly" if interval == "monthly" else "yearly"
        plan = self.client.plan.create(
            {
                "period": period,
                "interval": 1,
                "item": {
                    "name": f"CompliVibe {plan_name}",
                    "amount": amount_paise,
                    "currency": "INR",
                    "description": f"CompliVibe {plan_name} subscription",
                },
            }
        )
        return plan["id"]
