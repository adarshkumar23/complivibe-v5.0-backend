from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.organization import Organization
from app.models.risk import Risk
from app.models.user import User
from app.platform.services.billing_service import BillingService

# Category-A capped resources -> the model whose org-scoped rows count toward
# the Free-tier creation cap (features.record_caps). Keys match the record_caps
# keys seeded in DEFAULT_PLANS.
_CAPACITY_MODELS = {
    "policies": CompliancePolicy,
    "controls": Control,
    "evidence": EvidenceItem,
    "risks": Risk,
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _enforce_active_subscription(org: Organization) -> None:
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

    if org.subscription_status not in ("trial", "active"):
        frontend_url = get_settings().FRONTEND_URL
        raise HTTPException(
            status_code=402,
            detail={
                "error": "subscription_required",
                "message": f"Account status: {org.subscription_status}. Please update your subscription.",
                "billing_url": f"{frontend_url}/billing",
            },
        )


def require_active_subscription(
    # current_user resolves first so an unauthenticated request gets 401 before
    # get_current_organization's 400 (missing X-Organization-ID header).
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Organization:
    _enforce_active_subscription(org)
    return org


def _feature_denied(feature_name: str, plan: str) -> HTTPException:
    frontend_url = get_settings().FRONTEND_URL
    return HTTPException(
        status_code=403,
        detail={
            "error": "feature_not_in_plan",
            "feature": feature_name,
            "current_plan": plan,
            "message": f"'{feature_name}' is not available on the {plan} plan. Please upgrade to access this feature.",
            "upgrade_url": f"{frontend_url}/billing/upgrade",
        },
    )


def require_feature_for_writes(feature_name: str):
    """Category-B gate: feature-check WRITE methods only; reads pass through.

    Applied at the router level, this leaves GET/HEAD/OPTIONS ungated (RBAC on
    the endpoint still applies, so a Free org can view the domain) while
    POST/PUT/PATCH/DELETE require the plan feature. Trial and all paid tiers
    carry the flag TRUE, so only Free is write-blocked.
    """

    def _check(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
        x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    ) -> None:
        # Reads pass through untouched -- crucially WITHOUT resolving the org, so
        # this gate never adds an X-Organization-ID requirement to endpoints that
        # don't otherwise need one (e.g. global-catalog GETs). RBAC on the
        # endpoint still governs reads. (current_user is resolved so an
        # unauthenticated write yields 401, not 400.)
        if request.method not in _WRITE_METHODS:
            return None
        # Writes are org-scoped and already carry the header; resolve + enforce.
        org = get_current_organization(db=db, x_organization_id=x_organization_id)
        _enforce_active_subscription(org)
        if not BillingService(db).check_feature_access(org.id, feature_name):
            raise _feature_denied(feature_name, org.subscription_plan)
        return None

    return Depends(_check)


def require_capacity(resource: str):
    """Enforce the plan's per-resource creation cap on a create endpoint.

    Free tier caps core creation at 5 each (policies/controls/evidence/risks);
    trial and all paid plans carry record_caps={} -> uncapped (no-op). The count
    is strictly org-scoped. Deleting a record frees a slot (count-based, not a
    high-water mark). Apply ONLY to the four primary create paths.
    """
    model = _CAPACITY_MODELS[resource]  # fail fast at import/wire time on a typo

    def _check(
        org: Organization = Depends(get_current_organization),
        db: Session = Depends(get_db),
    ) -> Organization:
        cap = BillingService(db).record_cap_for(org.id, resource)
        if cap is None:
            return org  # uncapped plan -> no-op
        count = db.execute(
            select(func.count()).select_from(model).where(model.organization_id == org.id)
        ).scalar_one()
        if count >= cap:
            frontend_url = get_settings().FRONTEND_URL
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "record_cap_reached",
                    "resource": resource,
                    "cap": cap,
                    "current_count": count,
                    "current_plan": org.subscription_plan,
                    "message": (
                        f"The {org.subscription_plan} plan allows at most {cap} {resource}. "
                        f"Upgrade your plan to create more."
                    ),
                    "upgrade_url": f"{frontend_url}/billing/upgrade",
                },
            )
        return org

    return Depends(_check)


def require_feature(feature_name: str):
    def _check(
        org: Organization = Depends(require_active_subscription),
        db: Session = Depends(get_db),
    ) -> Organization:
        if not BillingService(db).check_feature_access(org.id, feature_name):
            raise _feature_denied(feature_name, org.subscription_plan)
        return org

    return Depends(_check)
