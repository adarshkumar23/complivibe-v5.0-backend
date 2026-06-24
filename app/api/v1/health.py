from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="API health check")
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "api-v1"}
