from fastapi import APIRouter

from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary() -> dict:
    summary = DashboardService().get_placeholder_summary()
    return summary.model_dump()
