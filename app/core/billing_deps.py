from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_active_user, get_current_organization, get_db
from app.models.organization import Organization
from app.models.user import User
from app.platform.services.billing_service import CAPACITY_MODELS, BillingService


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _enforce_active_subscription(org: Organization, db: Session) -> None:
    # Lazy trial lifecycle (1c-5): an expired trial is transitioned to Free
    # in-place (data kept, features re-lock) instead of hitting a 402 dead-end.
    # After this, the gate is evaluated against the Free plan. No-op for any
    # non-trial or unexpired-trial org. Concurrency-safe (atomic claim).
    BillingService(db).downgrade_trial_if_expired(org)

    if org.subscription_status not in ("trial", "active"):
        frontend_url = get_settings().FRONTEND_URL
        raise HTTPException(
            status_code=402,
            detail={
                "error": "subscription_required",
                "message": f"Account status: {org.subscription_status}. Please update your subscription.",
                "billing_url": f"{frontend_url}/dashboard/billing",
            },
        )


def require_active_subscription(
    # current_user resolves first so an unauthenticated request gets 401 before
    # get_current_organization's 400 (missing X-Organization-ID header).
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Organization:
    _enforce_active_subscription(org, db)
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
            "upgrade_url": f"{frontend_url}/dashboard/billing",
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
        _enforce_active_subscription(org, db)
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
    assert resource in CAPACITY_MODELS, f"unknown capped resource {resource!r}"  # fail fast at wire time

    def _check(
        org: Organization = Depends(get_current_organization),
        db: Session = Depends(get_db),
    ) -> Organization:
        billing = BillingService(db)
        # Lazy trial lifecycle: if this create is the first action after trial
        # expiry, downgrade to Free first so the Free record cap is enforced
        # (an expired-trial org that created 20 policies can't create a 21st).
        billing.downgrade_trial_if_expired(org)
        cap = billing.record_cap_for(org.id, resource)
        if cap is None:
            return org  # uncapped plan -> no-op
        # Same counting path as /billing/status record_usage -> can never disagree.
        count = billing.record_count(org.id, resource)
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
                    "upgrade_url": f"{frontend_url}/dashboard/billing",
                },
            )
        return org

    return Depends(_check)


def require_feature_except(feature_name: str, exclude_paths: tuple[str, ...], *, writes_only: bool = False):
    """Router-level feature gate that skips specific paths.

    For MIXED routers that combine session endpoints with public/machine ones
    (e.g. a public DSAR /submit or a machine X-CompliVibe-Key /events sink under
    the same prefix). Any request whose path contains one of ``exclude_paths`` is
    passed through untouched -- never resolving the org, so the gate adds no
    session/header requirement to the public/machine callers.

    writes_only=True gates only POST/PUT/PATCH/DELETE (Category B); False gates
    every method (Category C). Auth is resolved first (current_user) so an
    unauthenticated gated request yields 401 before any 400 missing-header.
    """

    def _check(
        request: Request,
        db: Session = Depends(get_db),
        x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    ) -> None:
        # Path exclusion is checked FIRST, using only `request` -- no auth/session
        # dependency is injected, so excluded public/machine endpoints (which have
        # no Bearer token) are never touched. (Injecting get_current_active_user
        # here would make FastAPI resolve HTTPBearer -> 403 before this runs,
        # breaking every excluded machine/public caller.)
        path = request.url.path
        if any(excluded in path for excluded in exclude_paths):
            return None
        if writes_only and request.method not in _WRITE_METHODS:
            return None
        # Non-excluded: plan check only. The endpoint's own require_permission
        # still enforces authentication + membership, so we don't re-auth here.
        org = get_current_organization(db=db, x_organization_id=x_organization_id)
        _enforce_active_subscription(org, db)
        if not BillingService(db).check_feature_access(org.id, feature_name):
            raise _feature_denied(feature_name, org.subscription_plan)
        return None

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
