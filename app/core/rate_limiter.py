from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid

import limits as limits_lib
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models.rate_limit_config import RateLimitConfig

logger = logging.getLogger(__name__)


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
    # Email-triggering endpoints (queue an outbox row / test-send). Deliberately tight
    # so an authenticated insider cannot fan out mail at the loose api_general rate;
    # real admin usage (a few queued mails / a test send) stays well under it.
    "email": "20/minute",
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

        # Per-(org, endpoint_group) resolved-limit cache. The DB lookup in
        # get_org_limit used to run synchronously on the async event loop for
        # EVERY org-scoped request (see app/main.py), serializing the whole
        # server behind one blocking query and capping throughput. Caching the
        # resolved "N/minute" string for a short TTL turns the hot path into an
        # in-memory dict read; on a miss the DB query is run off the event loop
        # (asyncio.to_thread) so it still never blocks the loop.
        self._limit_cache: dict[tuple[str, str], tuple[str, float]] = {}
        self._cache_lock = threading.Lock()

        # Cross-worker cache invalidation via Redis pub/sub. The per-process TTL
        # cache above keeps the hot path in-memory (no per-request Redis round-trip
        # -- preserving the throughput fix); this channel propagates an admin's
        # limit change to EVERY worker in ~ms, so the config-cache TTL is only a
        # fallback bound when Redis is unavailable rather than the routine
        # cross-worker staleness window. Redis-backed request COUNTING (which makes
        # the per-worker limit shared, closing the N-workers = N*limit bypass) is
        # handled separately by slowapi via the storage_uri set above.
        self._redis_pub = None
        self._sub_stop = threading.Event()
        if settings.RATE_LIMIT_REDIS_URL:
            self._start_invalidation_pubsub(settings.RATE_LIMIT_REDIS_URL)

    _INVALIDATE_CHANNEL = "cv:ratelimit:invalidate"

    def _start_invalidation_pubsub(self, redis_url: str) -> None:
        """Connect the publisher and start the subscriber thread (best-effort).

        On any failure the limiter degrades to TTL-only cross-worker consistency
        (unchanged prior behavior) -- it never blocks startup or the request path.
        """
        try:
            import redis  # noqa: PLC0415 -- optional dependency, only needed with Redis

            self._redis_pub = redis.Redis.from_url(redis_url, socket_connect_timeout=5)
            self._redis_pub.ping()
            thread = threading.Thread(
                target=self._run_invalidation_subscriber,
                args=(redis_url,),
                name="ratelimit-invalidate-sub",
                daemon=True,
            )
            thread.start()
        except Exception as exc:  # noqa: BLE001 -- degrade to TTL, never crash the worker
            logger.warning(
                "rate-limit Redis pub/sub unavailable (%s); cross-worker invalidation "
                "falls back to the %ss config TTL",
                exc,
                self._cache_ttl,
            )
            self._redis_pub = None

    def _run_invalidation_subscriber(self, redis_url: str) -> None:
        """Listen for invalidation messages from other workers and clear the local
        cache accordingly. Reconnects with backoff; local-only clear (never
        re-publishes) so a message can't loop."""
        import redis  # noqa: PLC0415

        while not self._sub_stop.is_set():
            try:
                client = redis.Redis.from_url(redis_url, socket_connect_timeout=5)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(self._INVALIDATE_CHANNEL)
                for message in pubsub.listen():
                    if self._sub_stop.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    try:
                        payload = json.loads(message["data"])
                        self._invalidate_local(payload.get("org"), payload.get("group"))
                    except Exception:  # noqa: BLE001 -- one bad message must not kill the loop
                        logger.exception("rate-limit invalidation message handling failed")
            except Exception as exc:  # noqa: BLE001 -- reconnect on any transport error
                logger.warning("rate-limit invalidation subscriber disconnected (%s); retrying", exc)
                time.sleep(2)

    @property
    def _cache_ttl(self) -> float:
        return float(get_settings().RATE_LIMIT_CONFIG_CACHE_TTL_SECONDS)

    def _cache_get(self, cache_key: tuple[str, str]) -> str | None:
        with self._cache_lock:
            entry = self._limit_cache.get(cache_key)
            if entry is None:
                return None
            limit_str, expires_at = entry
            if time.monotonic() >= expires_at:
                # Expired: drop it so the dict does not grow unbounded with stale keys.
                self._limit_cache.pop(cache_key, None)
                return None
            return limit_str

    def _cache_put(self, cache_key: tuple[str, str], limit_str: str) -> None:
        with self._cache_lock:
            self._limit_cache[cache_key] = (limit_str, time.monotonic() + self._cache_ttl)

    def _invalidate_local(self, org_id: uuid.UUID | str | None, endpoint_group: str | None = None) -> None:
        """Clear THIS process's cached limits for an org. No Redis publish (so a
        received pub/sub message can't loop)."""
        if org_id is None:
            return
        org_str = str(org_id)
        with self._cache_lock:
            for key in [k for k in self._limit_cache if k[0] == org_str and (endpoint_group is None or k[1] == endpoint_group)]:
                self._limit_cache.pop(key, None)

    def invalidate_org(self, org_id: uuid.UUID | str, endpoint_group: str | None = None) -> None:
        """Drop cached limits for an org after its config changes.

        Called in-process from RateLimitService when a limit is set or reset. The
        local cache is cleared immediately so the change takes effect in THIS
        worker at once; when Redis is configured the change is also published on
        ``_INVALIDATE_CHANNEL`` so every OTHER worker clears its cache in ~ms
        (closing the cross-worker staleness that otherwise lasts up to the config
        TTL). With ``endpoint_group`` None, every group for the org is dropped. If
        Redis is unavailable the publish is skipped and other workers fall back to
        the TTL bound (prior behavior).
        """
        org_str = str(org_id)
        self._invalidate_local(org_str, endpoint_group)
        if self._redis_pub is not None:
            try:
                self._redis_pub.publish(
                    self._INVALIDATE_CHANNEL,
                    json.dumps({"org": org_str, "group": endpoint_group}),
                )
            except Exception as exc:  # noqa: BLE001 -- local clear already done; degrade to TTL
                logger.warning(
                    "rate-limit invalidation publish failed (%s); other workers fall back to TTL",
                    exc,
                )

    def clear_limit_cache(self) -> None:
        """Wipe the whole resolved-limit cache (used by test fixtures for isolation)."""
        with self._cache_lock:
            self._limit_cache.clear()

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
        if path.startswith("/api/v1/email/") or path.endswith("/email-config/test"):
            return "email"
        if path.startswith("/api/v1/ai-governance/"):
            return "ai_governance"
        if (
            path.startswith("/api/v1/trust-center/")
            # The whistleblower hotline is unauthenticated by design: anyone on the
            # internet can submit, check status, or reply with only a tracking code.
            # It previously fell through to api_general (300/min), the loosest bucket
            # on the platform, despite carrying its most sensitive content.
            or path.startswith("/api/v1/whistleblower/")
            or path == "/api/v1/privacy/ccpa/opt-out"
            or path == "/api/v1/privacy/dsr/submit"
            or path.endswith("/metadata") and "/auth/sso/" in path
        ):
            return "public"
        return "api_general"

    def _hit_fail_open(self, item: limits_lib.RateLimitItem, endpoint_group: str, key: str) -> bool:
        """Register a hit against the counter, failing OPEN on any storage error.

        With in-memory storage this never raises. With Redis-backed storage
        (RATE_LIMIT_REDIS_URL set) a Redis outage would otherwise raise here and,
        because this runs in the request middleware, 500 EVERY request. Rate
        limiting is a protective control, not a correctness one, so a storage
        outage degrades to "temporarily unlimited" (logged) rather than a total
        API outage.
        """
        try:
            return self.limiter._limiter.hit(item, "general", endpoint_group, key)
        except Exception as exc:  # noqa: BLE001 -- storage down: fail OPEN, never take down the API
            logger.warning("rate-limit storage error on hit(); allowing request (fail-open): %s", exc)
            return True

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
        allowed = self._hit_fail_open(item, endpoint_group, key)
        return allowed, endpoint_group, limit_str

    def get_org_limit(self, org_id: uuid.UUID, endpoint_group: str, db: Session) -> str:
        """Resolve the "N/minute" limit for (org, group), cache-first.

        A cache hit avoids the DB entirely. On a miss the DB is queried via the
        provided session and the result cached for RATE_LIMIT_CONFIG_CACHE_TTL_SECONDS.
        Keyed by the concrete org_id, so a value resolved for org A (even the
        global-default fallback) is NEVER served to org B.
        """
        cache_key = (str(org_id), endpoint_group)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        limit_str = self._query_org_limit(org_id, endpoint_group, db)
        self._cache_put(cache_key, limit_str)
        return limit_str

    def _query_org_limit(self, org_id: uuid.UUID, endpoint_group: str, db: Session) -> str:
        """The raw DB resolution: org-specific override -> global default row -> code default."""
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

    def _resolve_org_limit_in_thread(self, org_id: uuid.UUID, endpoint_group: str) -> str:
        """Run inside a worker thread (never the event loop): open our OWN session,
        resolve+cache the limit, and always close the session."""
        db = get_session_maker()()
        try:
            return self.get_org_limit(org_id, endpoint_group, db)
        finally:
            db.close()

    async def check_general_limit_async(self, request: Request) -> tuple[bool, str, str]:
        """Async-safe equivalent of check_general_limit for the request middleware.

        The limit-config lookup is served from the in-memory TTL cache on the hot
        path (no DB, no thread hop); only a cache miss touches the DB, and that
        query is pushed off the event loop via asyncio.to_thread so a blocking
        SQLAlchemy call never serializes the loop. The counter .hit() stays inline
        (in-memory, or a fast local Redis op when RATE_LIMIT_REDIS_URL is set).
        """
        endpoint_group = getattr(request.state, "endpoint_group", None) or self.endpoint_group_for_path(request.url.path)
        limit_str = ENDPOINT_GROUP_DEFAULTS.get(endpoint_group, ENDPOINT_GROUP_DEFAULTS["api_general"])

        org_id = getattr(request.state, "organization_id", None)
        if org_id:
            try:
                oid = uuid.UUID(str(org_id))
            except (ValueError, TypeError):
                oid = None
            if oid is not None:
                cached = self._cache_get((str(oid), endpoint_group))
                if cached is not None:
                    limit_str = cached
                else:
                    limit_str = await asyncio.to_thread(self._resolve_org_limit_in_thread, oid, endpoint_group)

        item = limits_lib.parse(limit_str)
        key = self._get_rate_key(request)
        allowed = self._hit_fail_open(item, endpoint_group, key)
        return allowed, endpoint_group, limit_str


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
