from __future__ import annotations

import hashlib
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.rate_limit_config import RateLimitConfig


ENDPOINT_GROUP_DEFAULTS: dict[str, str] = {
    "api_general": "60/minute",
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
