from pydantic import BaseModel


class DashboardSummary(BaseModel):
    open_obligations: int = 0
    open_risks: int = 0
    pending_tasks: int = 0
    current_score: int | None = None
