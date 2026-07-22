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


# NOTE: these razorpay_plan_id / razorpay_annual_plan_id values are PLACEHOLDERS
# following Razorpay's real plan-ID format (`plan_` + 14 alphanumeric characters).
# They let the subscribe flow reach the point of actually calling Razorpay with a
# configured plan mapping instead of failing locally beforehand -- they are NOT real
# Razorpay plan IDs and MUST be replaced with the actual IDs created in the
# production Razorpay dashboard (Plans -> Create Plan, one per plan_code x billing
# cycle) before this can process real payments.
DEFAULT_PLANS: dict[str, dict] = {
    "free": {
        "display_name": "Free",
        "price_inr_monthly": 0,
        "price_inr_annual": 0,
        "max_users": 3,
        "max_frameworks": 1,
        "max_ai_systems": 0,
        "max_dsr_per_month": 0,
        "features": {
            "max_users": 3,
            "max_frameworks": 1,
            "max_ai_systems": 0,
            "max_dsr_per_month": 0,
            "api_access": False,
            "audit_log_days": 7,
            "support": "none",
            # Free record caps: 5 each of the four core compliance resources.
            # Enforced by require_capacity() in Stage 1c-3 (not yet wired).
            "record_caps": {"policies": 5, "controls": 5, "evidence": 5, "risks": 5},
            # Existing premium flags
            "sso_enabled": False,
            "scim_enabled": False,
            "siem_export": False,
            "ai_policy_drafting": False,
            "ai_risk_recommendations": False,
            # New Category B (write-gated) flags
            "privacy_basic": True,
            "vendor_management": False,
            "framework_activation": False,
            "workflow_management": False,
            "attestation_management": False,
            # New Category C (router-locked) flags
            "ai_governance_module": False,
            "governance_autopilot": False,
            "resilience_module": False,
            "privacy_advanced": False,
            "audit_assurance": False,
            "advanced_analytics": False,
            "advanced_reporting": False,
            "integrations_module": False,
            "questionnaire_management": False,
            "identity_governance": False,
            "specialized_modules": False,
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
        "razorpay_plan_id": None,
        "razorpay_annual_plan_id": None,
    },
    "trial": {
        "display_name": "Trial",
        "price_inr_monthly": 0,
        "price_inr_annual": 0,
        "max_users": None,
        "max_frameworks": None,
        "max_ai_systems": None,
        "max_dsr_per_month": None,
        "features": {
            # Trial = enterprise-equivalent: every flag TRUE, no record caps,
            # time-boxed by organizations.trial_ends_at (+TRIAL_DAYS).
            "max_users": None,
            "max_frameworks": None,
            "max_ai_systems": None,
            "max_dsr_per_month": None,
            "api_access": True,
            "audit_log_days": 730,
            "support": "email",
            "record_caps": {},
            "sso_enabled": True,
            "scim_enabled": True,
            "siem_export": True,
            "ai_policy_drafting": True,
            "ai_risk_recommendations": True,
            "privacy_basic": True,
            "vendor_management": True,
            "framework_activation": True,
            "workflow_management": True,
            "attestation_management": True,
            "ai_governance_module": True,
            "governance_autopilot": True,
            "resilience_module": True,
            "privacy_advanced": True,
            "audit_assurance": True,
            "advanced_analytics": True,
            "advanced_reporting": True,
            "integrations_module": True,
            "questionnaire_management": True,
            "identity_governance": True,
            "specialized_modules": True,
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
        "razorpay_plan_id": None,
        "razorpay_annual_plan_id": None,
    },
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
            "record_caps": {},
            "privacy_basic": True,
            "vendor_management": True,
            "framework_activation": True,
            "workflow_management": True,
            "attestation_management": True,
            "ai_governance_module": False,
            "governance_autopilot": False,
            "resilience_module": False,
            "privacy_advanced": True,
            "audit_assurance": False,
            "advanced_analytics": False,
            "advanced_reporting": False,
            "integrations_module": False,
            "questionnaire_management": True,
            "identity_governance": False,
            "specialized_modules": False,
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
        "razorpay_plan_id": "plan_STARTERMTHLY00",
        "razorpay_annual_plan_id": "plan_STARTERANNUL00",
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
            "record_caps": {},
            "privacy_basic": True,
            "vendor_management": True,
            "framework_activation": True,
            "workflow_management": True,
            "attestation_management": True,
            "ai_governance_module": True,
            "governance_autopilot": False,
            "resilience_module": True,
            "privacy_advanced": True,
            "audit_assurance": True,
            "advanced_analytics": True,
            "advanced_reporting": True,
            "integrations_module": True,
            "questionnaire_management": True,
            "identity_governance": False,
            "specialized_modules": False,
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
        "razorpay_plan_id": "plan_GROWTHMTHLY000",
        "razorpay_annual_plan_id": "plan_GROWTHANNUL000",
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
            "record_caps": {},
            "privacy_basic": True,
            "vendor_management": True,
            "framework_activation": True,
            "workflow_management": True,
            "attestation_management": True,
            "ai_governance_module": True,
            "governance_autopilot": True,
            "resilience_module": True,
            "privacy_advanced": True,
            "audit_assurance": True,
            "advanced_analytics": True,
            "advanced_reporting": True,
            "integrations_module": True,
            "questionnaire_management": True,
            "identity_governance": True,
            "specialized_modules": True,
        },
        "plan_type": "fixed",
        "usage_unit_price_inr": None,
        "usage_weights_json": {},
        "razorpay_plan_id": "plan_ENTERPRMTHLY00",
        "razorpay_annual_plan_id": "plan_ENTERPRANNUL00",
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
            "record_caps": {},
            "privacy_basic": True,
            "vendor_management": True,
            "framework_activation": True,
            "workflow_management": True,
            "attestation_management": True,
            "ai_governance_module": True,
            "governance_autopilot": True,
            "resilience_module": True,
            "privacy_advanced": True,
            "audit_assurance": True,
            "advanced_analytics": True,
            "advanced_reporting": True,
            "integrations_module": True,
            "questionnaire_management": True,
            "identity_governance": True,
            "specialized_modules": True,
        },
        "plan_type": "usage_based",
        "usage_unit_price_inr": 12.0,
        "usage_weights_json": {
            "active_framework_weight": 2.0,
            "active_user_weight": 1.0,
            "api_calls_per_unit": 1000.0,
            "api_call_weight": 0.5,
        },
        "razorpay_plan_id": "plan_USGFLEXMTHLY00",
        "razorpay_annual_plan_id": "plan_USGFLEXANNUL00",
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
        existing_rows = self.db.execute(select(SubscriptionPlan)).scalars().all()
        existing_by_code = {row.plan_code: row for row in existing_rows}
        for code, data in DEFAULT_PLANS.items():
            existing_row = existing_by_code.get(code)
            if existing_row is not None:
                # Backfill plan-ID mapping on already-seeded rows created before this
                # mapping existed, so previously-provisioned installs aren't stuck with
                # a permanently-unconfigured plan just because the row already existed.
                if not existing_row.razorpay_plan_id and data.get("razorpay_plan_id"):
                    existing_row.razorpay_plan_id = data["razorpay_plan_id"]
                if not existing_row.razorpay_annual_plan_id and data.get("razorpay_annual_plan_id"):
                    existing_row.razorpay_annual_plan_id = data["razorpay_annual_plan_id"]
                # Sync feature/limit fields from the DEFAULT_PLANS code constant so a
                # plan row seeded by an older code version doesn't permanently drift
                # from the plan definition (e.g. a new feature flag added to a plan
                # never reaching pre-existing DBs). DEFAULT_PLANS is the single source
                # of truth for plan definitions -- there is no admin UI/API that lets
                # operators hand-edit an individual plan row's features, so it is
                # always safe to overwrite these fields wholesale on every call.
                if existing_row.features != data["features"]:
                    existing_row.features = data["features"]
                if existing_row.max_users != data["max_users"]:
                    existing_row.max_users = data["max_users"]
                if existing_row.max_frameworks != data["max_frameworks"]:
                    existing_row.max_frameworks = data["max_frameworks"]
                if existing_row.max_ai_systems != data["max_ai_systems"]:
                    existing_row.max_ai_systems = data["max_ai_systems"]
                if existing_row.max_dsr_per_month != data["max_dsr_per_month"]:
                    existing_row.max_dsr_per_month = data["max_dsr_per_month"]
                if existing_row.display_name != data["display_name"]:
                    existing_row.display_name = data["display_name"]
                if existing_row.price_inr_monthly != data["price_inr_monthly"]:
                    existing_row.price_inr_monthly = data["price_inr_monthly"]
                if existing_row.price_inr_annual != data["price_inr_annual"]:
                    existing_row.price_inr_annual = data["price_inr_annual"]
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
                    razorpay_plan_id=data.get("razorpay_plan_id"),
                    razorpay_annual_plan_id=data.get("razorpay_annual_plan_id"),
                    max_users=data["max_users"],
                    max_frameworks=data["max_frameworks"],
                    max_ai_systems=data["max_ai_systems"],
                    max_dsr_per_month=data["max_dsr_per_month"],
                    features=data["features"],
                    is_active=True,
                )
            )
        self.db.flush()

    def start_free(self, org_id: uuid.UUID) -> None:
        """Land an organization on the Free plan (active, no trial).

        This is the default state for a self-registered org. Free is a real
        plan (plan_code="free", status="active") with capped core creation and
        no premium features -- NOT a trial. A trial is started only by
        redeeming a single-use trial code (Stage 1c-2), which calls
        start_trial() and sets trial_ends_at.
        """
        org = self.db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
        org.subscription_plan = "free"
        org.subscription_status = "active"
        org.trial_ends_at = None
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

        if org.subscription_status not in ("active", "trial"):
            return False
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
