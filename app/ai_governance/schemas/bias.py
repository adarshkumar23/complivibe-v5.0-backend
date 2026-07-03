import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BiasAssessmentCreate(BaseModel):
    assessment_method: str
    protected_attribute: str
    metric_name: str
    metric_value: float
    threshold_value: float
    lower_is_better: bool = True
    remediation_notes: str | None = None


class BiasAssessmentResponse(BaseModel):
    id: uuid.UUID
    system_id: uuid.UUID
    assessment_method: str
    protected_attribute: str
    metric_name: str
    metric_value: float
    threshold_value: float
    passed: bool
    remediation_notes: str | None
    assessed_at: datetime


class OversightUpdateRequest(BaseModel):
    oversight_level: str = Field(pattern="^(full_automation|human_on_loop|human_in_loop|human_in_command)$")
    explainability_method: str | None = Field(
        default=None,
        pattern="^(shap|lime|integrated_gradients|counterfactual|rule_based|none)$",
    )
