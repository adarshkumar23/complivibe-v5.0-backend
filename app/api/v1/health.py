from fastapi import APIRouter, Response
from sqlalchemy import text

from app.db.session import get_session_maker

router = APIRouter(tags=["health"])


@router.get("/health", summary="API health check")
def api_health(response: Response) -> dict[str, str]:
    try:
        db = get_session_maker()()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - report any DB failure as unhealthy
        response.status_code = 503
        return {"status": "error", "service": "api-v1", "detail": f"database unavailable: {exc}"}
    return {"status": "ok", "service": "api-v1"}
