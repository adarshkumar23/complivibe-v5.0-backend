from app.schemas.dashboard import DashboardSummary


class DashboardService:
    def get_placeholder_summary(self) -> DashboardSummary:
        return DashboardSummary()
