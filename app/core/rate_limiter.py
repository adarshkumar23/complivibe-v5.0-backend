from __future__ import annotations

import hashlib
import time
import uuid

import limits as limits_lib
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.rate_limit_config import RateLimitConfig


ENDPOINT_GROUP_DEFAULTS: dict[str, str] = {
    # A single dashboard page load fires 4-8 parallel queries against this group,
    # and normal navigation through several pages within a minute is completely
    # legitimate usage -- 60/minute measurably tripped on real multi-page
    # navigation in live verification passes, degrading every widget on the next
    # page to an "Unable to load" error for a real, non-abusive user. 300/minute
    # comfortably covers real usage (~40+ page loads/minute) while a genuine
    # abuse pattern (rapid identical requests, hundreds within seconds) still
    # exceeds it well within the same window.
    "api_general": "300/minute",
    "ingest": "30/minute",
    "auth": "10/minute",
    "reports": "20/minute",
    "public": "120/minute",
    "ai_governance": "30/minute",
    "scim": "60/minute",
}


class CompliVibeRateLimiter:
    """
    Wraps slowapi Limiter with org-aware keying.
    For JWT endpoints: key = org_id:user_id.
    For API-key endpoints: key = hashed API key.
    For public endpoints: key = remote address.
    """

    def __init__(self) -> None:
        settings = get_settings()
        limiter_kwargs: dict = {
            "key_func": self._get_rate_key,
            "default_limits": [ENDPOINT_GROUP_DEFAULTS["api_general"]],
        }
        if settings.RATE_LIMIT_REDIS_URL:
            limiter_kwargs["storage_uri"] = settings.RATE_LIMIT_REDIS_URL
        self.limiter = Limiter(**limiter_kwargs)

    def _get_rate_key(self, request: Request) -> str:
        org_id = getattr(request.state, "organization_id", None)
        if org_id:
            user_id = getattr(request.state, "user_id", "anon")
            return f"org:{org_id}:user:{user_id}"

        api_key = request.headers.get("X-CompliVibe-Key", "")
        if api_key:
            key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
            return f"apikey:{key_hash}"

        return f"ip:{get_remote_address(request)}"

    @staticmethod
    def endpoint_group_for_path(path: str) -> str:
        if path.startswith("/api/v1/auth/"):
            return "auth"
        if path.startswith("/api/v1/security/ingest/"):
            return "ingest"
        if path.startswith("/api/v1/scim/v2/") or path.startswith("/api/v1/scim/") or path.startswith("/scim/v2/"):
            return "scim"
        if path.startswith("/api/v1/compliance/reports/"):
            return "reports"
        if path.startswith("/api/v1/ai-governance/"):
            return "ai_governance"
        if (
            path.startswith("/api/v1/trust-center/")
            or path == "/api/v1/privacy/ccpa/opt-out"
            or path == "/api/v1/privacy/dsr/submit"
            or path.endswith("/metadata") and "/auth/sso/" in path
        ):
            return "public"
        return "api_general"

    def check_general_limit(self, request: Request, db: Session | None) -> tuple[bool, str, str]:
        """Enforce the general per-request rate limit for every request.

        slowapi's `SlowAPIMiddleware` relies on `default_limits` plus scanning
        `app.routes` at request time to find the matching endpoint handler and
        decide whether a route-specific limit applies. In this app, `/api/v1/*`
        routes are registered via a router included with FastAPI's lazy
        include-router mechanism, which `SlowAPIMiddleware`'s route scan does not
        see -- it only finds a handler (and therefore only ever enforces
        `default_limits`) for routes attached directly on the app object. As a
        result `default_limits` never actually applied to any `/api/v1/*` route;
        only endpoints with their own explicit `@rate_limiter.limiter.limit(...)`
        decorator (login/register/roi-calculator) were ever rate limited.
        This performs the same limit check slowapi's middleware was meant to do
        -- same key function, same per-endpoint-group defaults, same per-org
        overrides, same underlying storage/strategy -- but invoked directly from
        our own request-scoped middleware (see `app.main`), which runs for every
        request regardless of how its route was registered.
        """
        endpoint_group = getattr(request.state, "endpoint_group", None) or self.endpoint_group_for_path(request.url.path)
        limit_str = ENDPOINT_GROUP_DEFAULTS.get(endpoint_group, ENDPOINT_GROUP_DEFAULTS["api_general"])

        org_id = getattr(request.state, "organization_id", None)
        if org_id and db is not None:
            try:
                limit_str = self.get_org_limit(uuid.UUID(str(org_id)), endpoint_group, db)
            except (ValueError, TypeError):
                pass

        item = limits_lib.parse(limit_str)
        key = self._get_rate_key(request)
        allowed = self.limiter._limiter.hit(item, "general", endpoint_group, key)
        return allowed, endpoint_group, limit_str

    def get_org_limit(self, org_id: uuid.UUID, endpoint_group: str, db: Session) -> str:
        config = (
            db.query(RateLimitConfig)
            .filter(
                RateLimitConfig.organization_id == org_id,
                RateLimitConfig.endpoint_group == endpoint_group,
                RateLimitConfig.is_active.is_(True),
            )
            .first()
        )

        if config is None:
            config = (
                db.query(RateLimitConfig)
                .filter(
                    RateLimitConfig.organization_id.is_(None),
                    RateLimitConfig.endpoint_group == endpoint_group,
                    RateLimitConfig.is_active.is_(True),
                )
                .first()
            )

        if config is not None:
            return f"{config.requests_per_minute}/minute"

        return ENDPOINT_GROUP_DEFAULTS.get(endpoint_group, ENDPOINT_GROUP_DEFAULTS["api_general"])


rate_limiter = CompliVibeRateLimiter()


def build_rate_limit_exceeded_response(request: Request, detail: str) -> JSONResponse:
    endpoint_group = getattr(request.state, "endpoint_group", "api_general")
    raw_limit = str(detail or "60 per 1 minute")
    limit_value = "60/minute"
    retry_after = 60
    limit_per_minute = 60

    if " per " in raw_limit:
        pieces = raw_limit.split(" per ", 1)
        amount = pieces[0].strip()
        window = pieces[1].strip()
        if amount.isdigit():
            limit_per_minute = int(amount)
        if "minute" in window:
            retry_after = 60
            limit_value = f"{limit_per_minute}/minute"
        elif "hour" in window:
            retry_after = 3600
            limit_value = f"{limit_per_minute}/hour"
        elif "day" in window:
            retry_after = 86400
            limit_value = f"{limit_per_minute}/day"

    headers = {
        "Retry-After": str(retry_after),
        "X-RateLimit-Limit": str(limit_per_minute),
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(int(time.time()) + retry_after),
    }
    return JSONResponse(
        status_code=429,
        headers=headers,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests",
            "retry_after": retry_after,
            "limit": limit_value,
            "endpoint_group": endpoint_group,
        },
    )


def build_general_rate_limit_exceeded_response(endpoint_group: str, limit_str: str) -> JSONResponse:
    """Same response shape as `build_rate_limit_exceeded_response`, built directly
    from a "N/unit" limit string (as produced by `check_general_limit`) instead of
    slowapi's "N per M unit" exception detail string."""
    amount_str, _, unit = limit_str.partition("/")
    limit_per_minute = int(amount_str) if amount_str.isdigit() else 60
    retry_after = {"minute": 60, "hour": 3600, "day": 86400}.get(unit, 60)

    headers = {
        "Retry-After": str(retry_after),
        "X-RateLimit-Limit": str(limit_per_minute),
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(int(time.time()) + retry_after),
    }
    return JSONResponse(
        status_code=429,
        headers=headers,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests",
            "retry_after": retry_after,
            "limit": limit_str,
            "endpoint_group": endpoint_group,
        },
    )
