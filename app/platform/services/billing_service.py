from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.organization import Organization
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User
from app.platform.services.razorpay_service import RazorpayService
from app.services.audit_service import AuditService


DEFAULT_PLANS: dict[str, dict] = {
    "starter": {
        "display_name": "Starter",
        "price_inr_monthly": 499900,
        "price_inr_annual": 4799000,
        "max_users": 5,
        "max_frameworks": 3,
        "max_ai_systems": 2,
        "max_dsr_per_month": 10,
        "features": {
            "max_users": 5,
            "max_frameworks": 3,
            "max_ai_systems": 2,
            "max_dsr_per_month": 10,
            "sso_enabled": False,
            "scim_enabled": False,
            "siem_export": False,
            "ai_policy_drafting": False,
            "ai_risk_recommendations": False,
            "api_access": True,
            "audit_log_days": 90,
            "support": "email",
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
    },
    "growth": {
        "display_name": "Growth",
        "price_inr_monthly": 1499900,
        "price_inr_annual": 14399000,
        "max_users": 25,
        "max_frameworks": 10,
        "max_ai_systems": 10,
        "max_dsr_per_month": 100,
        "features": {
            "max_users": 25,
            "max_frameworks": 10,
            "max_ai_systems": 10,
            "max_dsr_per_month": 100,
            "sso_enabled": True,
            "scim_enabled": False,
            "siem_export": True,
            "ai_policy_drafting": True,
            "ai_risk_recommendations": True,
            "api_access": True,
            "audit_log_days": 365,
            "support": "priority_email",
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
    },
    "enterprise": {
        "display_name": "Enterprise",
        "price_inr_monthly": 4999900,
        "price_inr_annual": 47999000,
        "max_users": None,
        "max_frameworks": None,
        "max_ai_systems": None,
        "max_dsr_per_month": None,
        "features": {
            "max_users": None,
            "max_frameworks": None,
            "max_ai_systems": None,
            "max_dsr_per_month": None,
            "sso_enabled": True,
            "scim_enabled": True,
            "siem_export": True,
            "ai_policy_drafting": True,
            "ai_risk_recommendations": True,
            "api_access": True,
            "audit_log_days": 730,
            "support": "dedicated_csm",
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
    },
    "usage_flex": {
        "display_name": "Usage Flex",
        "price_inr_monthly": 0,
        "price_inr_annual": 0,
        "max_users": None,
        "max_frameworks": None,
        "max_ai_systems": None,
        "max_dsr_per_month": None,
        "features": {
            "max_users": None,
            "max_frameworks": None,
            "max_ai_systems": None,
            "max_dsr_per_month": None,
            "sso_enabled": True,
            "scim_enabled": True,
            "siem_export": True,
            "ai_policy_drafting": True,
            "ai_risk_recommendations": True,
            "api_access": True,
            "audit_log_days": 730,
            "support": "priority_email",
        },
        "plan_type": "usage_based",
        "usage_unit_price_inr": 12.0,
        "usage_weights_json": {
            "active_framework_weight": 2.0,
            "active_user_weight": 1.0,
            "api_calls_per_unit": 1000.0,
            "api_call_weight": 0.5,
        },
    },
}


class BillingService:
    def __init__(self, db: Session):
        self.db = db
        self.rzp = RazorpayService()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def ensure_default_plans(self) -> None:
        existing = self.db.execute(select(SubscriptionPlan.plan_code)).scalars().all()
        existing_codes = set(existing)
        for code, data in DEFAULT_PLANS.items():
            if code in existing_codes:
                continue
            self.db.add(
                SubscriptionPlan(
                    plan_code=code,
                    display_name=data["display_name"],
                    plan_type=data.get("plan_type", "fixed"),
                    price_inr_monthly=data["price_inr_monthly"],
                    price_inr_annual=data["price_inr_annual"],
                    usage_unit_price_inr=data.get("usage_unit_price_inr"),
                    usage_weights_json=data.get("usage_weights_json", {}),
                    max_users=data["max_users"],
                    max_frameworks=data["max_frameworks"],
                    max_ai_systems=data["max_ai_systems"],
                    max_dsr_per_month=data["max_dsr_per_month"],
                    features=data["features"],
                    is_active=True,
                )
            )
        self.db.flush()

    def start_trial(self, org_id: uuid.UUID) -> None:
        org = self.db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
        settings = get_settings()
        org.subscription_status = "trial"
        org.subscription_plan = "starter"
        org.trial_ends_at = self.utcnow() + timedelta(days=settings.TRIAL_DAYS)
        self.db.flush()

    def initiate_subscription(
        self,
        org_id: uuid.UUID,
        plan_code: str,
        admin_user_id: uuid.UUID,
        billing_cycle: str = "monthly",
    ) -> dict:
        self.ensure_default_plans()

        org = self.db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")

        if org.subscription_status == "active" and org.razorpay_subscription_id and org.subscription_plan == plan_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Organization already has an active subscription to plan '{plan_code}'. "
                    "Cancel the existing subscription before starting a new one."
                ),
            )

        plan = self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.plan_code == plan_code,
                SubscriptionPlan.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{plan_code}' not found")

        plan_id = plan.razorpay_annual_plan_id if billing_cycle == "annual" else plan.razorpay_plan_id
        if not plan_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Razorpay plan ID not configured for {plan_code}. Run platform setup.",
            )

        if not org.razorpay_customer_id:
            admin = self.db.get(User, admin_user_id)
            if admin is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")
            try:
                org.razorpay_customer_id = self.rzp.create_customer(
                    org_id=org_id,
                    org_name=org.name,
                    admin_email=admin.email,
                    admin_name=admin.full_name or admin.email,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Payment processor error while creating customer profile. Please retry.",
                ) from exc
            self.db.flush()

        try:
            subscription = self.rzp.create_subscription(
                razorpay_customer_id=org.razorpay_customer_id,
                razorpay_plan_id=plan_id,
                org_id=org_id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Payment processor error while creating subscription. Please retry.",
            ) from exc

        org.razorpay_subscription_id = subscription["id"]
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="billing.subscription_initiated",
            entity_type="organizations",
            organization_id=org_id,
            actor_user_id=admin_user_id,
            entity_id=org_id,
            metadata_json={
                "plan": plan_code,
                "cycle": billing_cycle,
                "razorpay_sub_id": subscription["id"],
            },
        )

        return {
            "subscription_id": subscription["id"],
            "payment_url": subscription.get("short_url", ""),
            "plan": plan_code,
            "billing_cycle": billing_cycle,
            "message": "Redirect customer to payment_url to complete subscription setup",
        }

    def cancel_subscription(self, org_id: uuid.UUID, user_id: uuid.UUID, cancel_at_cycle_end: bool = True) -> dict:
        org = self.db.get(Organization, org_id)
        if not org or not org.razorpay_subscription_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active subscription found")
        if org.subscription_status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subscription is already cancelled",
            )

        try:
            self.rzp.cancel_subscription(org.razorpay_subscription_id, cancel_at_cycle_end=cancel_at_cycle_end)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Payment processor error while cancelling subscription. Please retry.",
            ) from exc

        if not cancel_at_cycle_end:
            org.subscription_status = "cancelled"
            self.db.flush()

        AuditService(self.db).write_audit_log(
            action="billing.subscription_cancelled",
            entity_type="organizations",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=org_id,
            metadata_json={"at_cycle_end": cancel_at_cycle_end},
        )

        return {
            "cancelled": True,
            "access_until": "end of current billing period" if cancel_at_cycle_end else "immediately",
        }

    def get_billing_status(self, org_id: uuid.UUID) -> dict:
        self.ensure_default_plans()

        org = self.db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")

        plan = self.db.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == org.subscription_plan)).scalar_one_or_none()
        features = plan.features if plan else {}

        is_trial = org.subscription_status == "trial"
        trial_days_remaining = None
        context_flags: list[str] = []
        now = self.utcnow()

        if is_trial and org.trial_ends_at:
            delta = self._as_utc(org.trial_ends_at) - now
            trial_days_remaining = max(0, delta.days)
            if delta.total_seconds() <= 0:
                context_flags.append("trial_expired_pending_downgrade")
            elif trial_days_remaining <= 3:
                context_flags.append("trial_ending_soon")

        if plan is None:
            context_flags.append("plan_not_found")
        elif not plan.is_active:
            context_flags.append("plan_inactive")

        renewal_days_remaining = None
        if org.subscription_ends_at:
            renewal_delta = self._as_utc(org.subscription_ends_at) - now
            renewal_days_remaining = renewal_delta.days
            if org.subscription_status == "active" and renewal_delta.total_seconds() > 0:
                context_flags.append("pending_cancellation_at_period_end")
            elif renewal_delta.total_seconds() <= 0 and org.subscription_status == "active":
                context_flags.append("subscription_period_ended_unprocessed")

        if org.subscription_status == "active" and not org.razorpay_subscription_id:
            context_flags.append("missing_payment_provider_link")

        if org.subscription_status not in ("active", "trial"):
            context_flags.append("no_active_access")

        return {
            "subscription_status": org.subscription_status,
            "plan": org.subscription_plan,
            "is_trial": is_trial,
            "trial_days_remaining": trial_days_remaining,
            "trial_ends_at": org.trial_ends_at.isoformat() if org.trial_ends_at else None,
            "subscription_ends_at": org.subscription_ends_at.isoformat() if org.subscription_ends_at else None,
            "renewal_days_remaining": renewal_days_remaining,
            "features": features,
            "razorpay_subscription_id": org.razorpay_subscription_id,
            "context_flags": sorted(set(context_flags)),
        }

    def list_plans(self) -> list[SubscriptionPlan]:
        self.ensure_default_plans()
        return self.db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.price_inr_monthly.asc())
        ).scalars().all()

    def get_invoices(self, org_id: uuid.UUID) -> list[dict]:
        org = self.db.get(Organization, org_id)
        if not org or not org.razorpay_subscription_id:
            return []

        invoices = self.rzp.get_invoices(org.razorpay_subscription_id)
        return [
            {
                "id": item.get("id"),
                "amount": item.get("amount", 0) / 100,
                "currency": item.get("currency", "INR"),
                "status": item.get("status"),
                "date": item.get("billing_start"),
                "pdf_url": item.get("short_url"),
            }
            for item in invoices
        ]

    def check_feature_access(self, org_id: uuid.UUID, feature: str) -> bool:
        self.ensure_default_plans()

        org = self.db.get(Organization, org_id)
        if not org:
            return False

        if org.subscription_status == "trial":
            plan_code = "starter"
        elif org.subscription_status not in ("active", "trial"):
            return False
        else:
            plan_code = org.subscription_plan

        plan = self.db.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_code)).scalar_one_or_none()
        if not plan:
            return False

        features = plan.features or {}
        if feature not in features:
            return False

        value = features[feature]
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        return bool(value)
