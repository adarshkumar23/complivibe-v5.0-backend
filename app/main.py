from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except Exception:  # pragma: no cover - optional in local test environments
    Instrumentator = None  # type: ignore[assignment]

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.pbc_scheduler import register_pbc_scheduler
from app.core.rate_limiter import build_rate_limit_exceeded_response, rate_limiter
from app.core.security import decode_access_token
from app.core.startup import register_event_listeners
from app.platform.routers.billing import webhook_router as billing_webhook_router


def _scrub_sensitive_data(event: dict) -> dict:
    sensitive_keys = {
        "password",
        "hashed_password",
        "token",
        "access_token",
        "api_key",
        "secret",
        "aws_secret_access_key",
        "razorpay_key_secret",
        "webhook_secret",
        "authorization",
        "x-complivibe-key",
    }

    def scrub(value):
        if isinstance(value, dict):
            return {
                key: ("[REDACTED]" if str(key).lower() in sensitive_keys else scrub(nested))
                for key, nested in value.items()
            }
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    if "request" in event:
        event["request"] = scrub(event["request"])
    if "extra" in event:
        event["extra"] = scrub(event["extra"])
    return event


def _configure_sentry() -> None:
    settings = get_settings()
    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
        before_send=lambda event, hint: _scrub_sensitive_data(event),
    )


_configure_sentry()


def create_application() -> FastAPI:
    settings = get_settings()
    rate_limit_active = settings.RATE_LIMIT_ENABLED and settings.APP_ENV != "test"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if Instrumentator is not None:
            Instrumentator().instrument(app).expose(app)
        yield

    app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)
    register_event_listeners()
    register_pbc_scheduler(app)
    app.state.limiter = rate_limiter.limiter
    app.state.limiter.enabled = rate_limit_active

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if rate_limit_active:
        @app.middleware("http")
        async def rate_limit_request_context(request: Request, call_next):
            request.state.organization_id = None
            request.state.user_id = None
            request.state.endpoint_group = rate_limiter.endpoint_group_for_path(request.url.path)
            request.state.limit = None

            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                try:
                    payload = decode_access_token(token)
                    request.state.user_id = payload.get("sub")
                except (ValueError, JWTError):
                    request.state.user_id = None

            org_header = request.headers.get("X-Organization-ID")
            if org_header:
                request.state.organization_id = org_header

            return await call_next(request)

        app.add_middleware(SlowAPIMiddleware)

        @app.exception_handler(RateLimitExceeded)
        async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
            return build_rate_limit_exceeded_response(request, str(getattr(exc, "detail", "")))

    @app.get("/", summary="Service metadata")
    def root() -> dict[str, str]:
        return {
            "service": settings.APP_NAME,
            "version": "0.1.0",
            "environment": settings.APP_ENV,
        }

    @app.get("/health", summary="System health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.APP_NAME}

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(billing_webhook_router)
    return app


app = create_application()
