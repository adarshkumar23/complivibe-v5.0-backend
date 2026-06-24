from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.startup import register_event_listeners


def create_application() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.APP_NAME, version="0.1.0")
    register_event_listeners()

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
