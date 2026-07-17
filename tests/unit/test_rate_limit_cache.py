"""Targeted tests for the per-org RateLimitConfig TTL cache that removes the
blocking DB lookup from the async request hot path.

Covers: (1) a cache hit avoids the DB entirely, (2) a config write invalidates
the cache so the new limit takes effect immediately, (3) NO cross-tenant bleed --
org A's cached limit is never served to org B, (4) the async check resolves from
cache without touching the DB, and (5) a stale entry expires after the TTL.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core.rate_limiter import rate_limiter
from app.platform.services.rate_limit_service import RateLimitService


@pytest.fixture
def defaults(db_session):
    RateLimitService().ensure_platform_defaults(db_session)
    db_session.flush()
    return db_session


def _fake_request(org_id: str | None, path: str = "/api/v1/controls", user_id: str = "u1"):
    state = SimpleNamespace(organization_id=org_id, user_id=user_id, endpoint_group=None)
    url = SimpleNamespace(path=path)
    return SimpleNamespace(state=state, url=url, headers={})


# ── 1. Cache hit avoids the DB ───────────────────────────────────────────────
def test_cache_hit_avoids_db_query(defaults, monkeypatch):
    db = defaults
    org = uuid.uuid4()
    calls = {"n": 0}
    real_query = rate_limiter._query_org_limit

    def counting_query(org_id, endpoint_group, session):
        calls["n"] += 1
        return real_query(org_id, endpoint_group, session)

    monkeypatch.setattr(rate_limiter, "_query_org_limit", counting_query)

    first = rate_limiter.get_org_limit(org, "api_general", db)
    second = rate_limiter.get_org_limit(org, "api_general", db)
    third = rate_limiter.get_org_limit(org, "api_general", db)

    assert first == second == third == "300/minute"  # platform default
    assert calls["n"] == 1, "second/third lookups must be served from cache, not the DB"


# ── 2. Config write invalidates the cache immediately ────────────────────────
def test_set_org_limit_invalidates_cache(client, db_session):
    from tests.helpers.auth_org import bootstrap_org_user

    RateLimitService().ensure_platform_defaults(db_session)
    org = bootstrap_org_user(client, email_prefix="rlc-inval")
    org_id = uuid.UUID(org["organization_id"])
    actor = uuid.UUID(org["user_id"])

    # prime the cache with the platform default
    assert rate_limiter.get_org_limit(org_id, "api_general", db_session) == "300/minute"

    # a real config write must drop the stale cache entry
    RateLimitService().set_org_limit(
        org_id=org_id, endpoint_group="api_general",
        requests_per_minute=42, requests_per_hour=600, created_by=actor, db=db_session,
    )
    db_session.flush()

    assert rate_limiter.get_org_limit(org_id, "api_general", db_session) == "42/minute"


# ── 3. No cross-tenant bleed ─────────────────────────────────────────────────
def test_no_cross_tenant_cache_bleed(client, db_session):
    from tests.helpers.auth_org import bootstrap_org_user

    RateLimitService().ensure_platform_defaults(db_session)
    org_a = bootstrap_org_user(client, email_prefix="rlc-a")
    org_b = bootstrap_org_user(client, email_prefix="rlc-b")
    a_id, b_id = uuid.UUID(org_a["organization_id"]), uuid.UUID(org_b["organization_id"])
    a_actor = uuid.UUID(org_a["user_id"])

    # org A gets a bespoke low limit; org B keeps the default
    RateLimitService().set_org_limit(
        org_id=a_id, endpoint_group="api_general",
        requests_per_minute=5, requests_per_hour=100, created_by=a_actor, db=db_session,
    )
    db_session.flush()

    # prime both into the cache
    assert rate_limiter.get_org_limit(a_id, "api_general", db_session) == "5/minute"
    assert rate_limiter.get_org_limit(b_id, "api_general", db_session) == "300/minute"

    # re-read from cache: A's value must never be served to B and vice-versa
    assert rate_limiter.get_org_limit(a_id, "api_general", db_session) == "5/minute"
    assert rate_limiter.get_org_limit(b_id, "api_general", db_session) == "300/minute"


# ── 4. Async check resolves from cache with no DB session ────────────────────
def test_async_check_uses_cache_without_db(defaults):
    db = defaults
    org = uuid.uuid4()
    # prime the cache
    rate_limiter.get_org_limit(org, "api_general", db)

    async def go():
        return await rate_limiter.check_general_limit_async(_fake_request(str(org)))

    allowed, group, limit_str = asyncio.run(go())
    assert group == "api_general"
    assert limit_str == "300/minute"
    assert allowed is True


# ── 5. Entry expires after the TTL ───────────────────────────────────────────
def test_cache_entry_expires_after_ttl(defaults, monkeypatch):
    db = defaults
    org = uuid.uuid4()
    monkeypatch.setattr(type(rate_limiter), "_cache_ttl", property(lambda self: 0.0))
    rate_limiter.get_org_limit(org, "api_general", db)
    # with a 0s TTL the entry is already stale -> a fresh get must re-query (not raise)
    assert rate_limiter._cache_get((str(org), "api_general")) is None
