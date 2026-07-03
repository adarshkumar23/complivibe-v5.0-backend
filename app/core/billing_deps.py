from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_organization, get_db
from app.models.organization import Organization
from app.platform.services.billing_service import BillingService


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def require_active_subscription(
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Organization:
    allowed_statuses = ("trial", "active")

    if org.subscription_status == "trial":
        now = datetime.now(UTC)
        if org.trial_ends_at and _as_utc(org.trial_ends_at) < now:
            frontend_url = get_settings().FRONTEND_URL
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "trial_expired",
                    "message": "Your 14-day trial has expired. Please subscribe to continue.",
                    "upgrade_url": f"{frontend_url}/billing/upgrade",
                },
            )

    if org.subscription_status not in allowed_statuses:
        frontend_url = get_settings().FRONTEND_URL
        raise HTTPException(
            status_code=402,
            detail={
                "error": "subscription_required",
                "message": f"Account status: {org.subscription_status}. Please update your subscription.",
                "billing_url": f"{frontend_url}/billing",
            },
        )

    return org


def require_feature(feature_name: str):
    def _check(
        org: Organization = Depends(require_active_subscription),
        db: Session = Depends(get_db),
    ) -> Organization:
        billing_svc = BillingService(db)
        if not billing_svc.check_feature_access(org.id, feature_name):
            plan = org.subscription_plan
            frontend_url = get_settings().FRONTEND_URL
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_in_plan",
                    "feature": feature_name,
                    "current_plan": plan,
                    "message": f"'{feature_name}' is not available on the {plan} plan. Please upgrade to access this feature.",
                    "upgrade_url": f"{frontend_url}/billing/upgrade",
                },
            )
        return org

    return Depends(_check)
