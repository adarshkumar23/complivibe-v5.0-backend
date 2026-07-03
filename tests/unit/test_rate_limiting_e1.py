from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import inspect, select

from app.core.rate_limiter import build_rate_limit_exceeded_response
from app.core.config import get_settings
from app.core.rate_limiter import rate_limiter
from app.main import create_application
from app.models.rate_limit_config import RateLimitConfig
from app.models.user import User
from app.platform.services.rate_limit_service import RateLimitService
from tests.helpers.auth_org import bootstrap_org_user


def _promote_superuser(db_session, user_id: str) -> None:
    user = db_session.get(User, UUID(user_id))
    assert user is not None
    user.is_superuser = True
    db_session.flush()


def test_rate_limit_config_defaults_and_table_exists(client, db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert "rate_limit_configs" in tables

    rows = RateLimitService().get_platform_defaults(db_session)
    assert len(rows) == 7

    by_group = {row.endpoint_group: row for row in rows}
    assert by_group["api_general"].requests_per_minute == 60
    assert by_group["auth"].requests_per_minute == 10
    assert by_group["ingest"].requests_per_minute == 30
    assert by_group["public"].requests_per_minute == 120


def test_admin_rate_limit_endpoints_superuser_only(client, db_session):
    admin_org = bootstrap_org_user(client, email_prefix="rl-admin")
    _promote_superuser(db_session, admin_org["user_id"])

    non_admin_org = bootstrap_org_user(client, email_prefix="rl-member")

    defaults_ok = client.get("/api/v1/admin/rate-limits/defaults", headers=admin_org["headers"])
    assert defaults_ok.status_code == 200
    assert len(defaults_ok.json()) == 7

    defaults_forbidden = client.get("/api/v1/admin/rate-limits/defaults", headers=non_admin_org["headers"])
    assert defaults_forbidden.status_code == 403


def test_set_org_limit_and_my_limits(client, db_session):
    admin_org = bootstrap_org_user(client, email_prefix="rl-set")
    _promote_superuser(db_session, admin_org["user_id"])

    target_org = bootstrap_org_user(client, email_prefix="rl-target")

    update = client.put(
        f"/api/v1/admin/rate-limits/org/{target_org['organization_id']}",
        headers=admin_org["headers"],
        json={"endpoint_group": "api_general", "rpm": 30, "rph": 600},
    )
    assert update.status_code == 200
    assert update.json()["requests_per_minute"] == 30

    stored = db_session.execute(
        select(RateLimitConfig).where(
            RateLimitConfig.organization_id == UUID(target_org["organization_id"]),
            RateLimitConfig.endpoint_group == "api_general",
            RateLimitConfig.is_active.is_(True),
        )
    ).scalar_one_or_none()
    assert stored is not None
    assert stored.requests_per_minute == 30

    my_limits = client.get("/api/v1/rate-limits/my-limits", headers=target_org["org_headers"])
    assert my_limits.status_code == 200
    assert my_limits.json()["limits"]

    my_limits_no_jwt = client.get("/api/v1/rate-limits/my-limits")
    assert my_limits_no_jwt.status_code == 401


def test_rate_limit_service_behaviors(client, db_session):
    service = RateLimitService()
    org = bootstrap_org_user(client, email_prefix="rl-service")
    org_id = UUID(org["organization_id"])
    actor_id = UUID(org["user_id"])

    assert service.get_org_config(org_id, db_session) == []

    first = service.set_org_limit(
        org_id=org_id,
        endpoint_group="ingest",
        requests_per_minute=25,
        requests_per_hour=300,
        created_by=actor_id,
        db=db_session,
    )
    assert first.requests_per_minute == 25

    second = service.set_org_limit(
        org_id=org_id,
        endpoint_group="ingest",
        requests_per_minute=40,
        requests_per_hour=700,
        created_by=actor_id,
        db=db_session,
    )
    assert second.id == first.id
    assert second.requests_per_minute == 40

    service.reset_to_default(org_id=org_id, endpoint_group="ingest", user_id=actor_id, db=db_session)
    refreshed = db_session.get(RateLimitConfig, first.id)
    assert refreshed is not None
    assert refreshed.is_active is False


def test_get_org_limit_falls_back_to_platform_default(db_session):
    service = RateLimitService()
    service.ensure_platform_defaults(db_session)
    unknown_org = UUID("00000000-0000-0000-0000-00000000abcd")

    limit_value = rate_limiter.get_org_limit(unknown_org, "auth", db_session)
    assert limit_value == "10/minute"


def test_rate_limit_429_shape_and_headers():
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "GET",
            "path": "/api/v1/auth/login",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.endpoint_group = "auth"
    response = build_rate_limit_exceeded_response(request, "10 per 1 minute")

    assert response.status_code == 429
    import json

    body = json.loads(response.body.decode("utf-8"))
    assert body["error"] == "rate_limit_exceeded"
    assert body["endpoint_group"] == "auth"
    assert body["limit"] == "10/minute"

    headers = dict(response.headers)
    assert "retry-after" in headers
    assert "x-ratelimit-limit" in headers


def test_rate_limit_bypass_when_disabled(monkeypatch, db_session):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    from app.core.deps import get_db

    app = create_application()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as local_client:
        payload = {"email": "unknown@example.com", "password": "wrong"}
        statuses = [local_client.post("/api/v1/auth/login", json=payload).status_code for _ in range(20)]

    assert 429 not in statuses
    get_settings.cache_clear()


def test_settings_defaults_exist():
    settings = get_settings()
    assert settings.RATE_LIMIT_ENABLED is True
    assert settings.RATE_LIMIT_REDIS_URL is None
