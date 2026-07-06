from pydantic import BaseModel, Field


CURRENT_TOOL_PATTERN = "^(vanta|drata|sprinto|scrut|onetrust|credo_ai|generic|other)$"


class ROICalculatorRequest(BaseModel):
    current_tool: str = Field(pattern=CURRENT_TOOL_PATTERN)
    team_size: int = Field(ge=1, le=5000)
    frameworks_count: int = Field(ge=1, le=200)
    current_annual_cost: float = Field(ge=0, le=1_000_000_000)


class ROICalculatorResponse(BaseModel):
    hours_saved_per_week: float
    annual_saving: float
    payback_period_months: float | None = None
    three_year_roi_pct: float
