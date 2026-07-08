from datetime import datetime

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    open_obligations: int = 0
    open_risks: int = 0
    pending_tasks: int = 0
    current_score: int | None = None
    current_score_grade: str | None = None
    current_score_calculated_at: datetime | None = None
    total_controls: int = 0
    total_vendors: int = 0
    total_policies: int = 0
