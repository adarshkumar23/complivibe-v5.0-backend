from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except Exception:  # pragma: no cover - optional in local test environments
    Instrumentator = None  # type: ignore[assignment]

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.pbc_scheduler import register_pbc_scheduler
from app.core.startup import register_event_listeners


def create_application() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if Instrumentator is not None:
            Instrumentator().instrument(app).expose(app)
        yield

    app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)
    register_event_listeners()
    register_pbc_scheduler(app)

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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
    return app


app = create_application()
