from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

AI_VENDOR_ASSESSMENT_STATUS_PATTERN = "^(draft|in_progress|completed|archived)$"
AI_VENDOR_MODEL_TYPE_PATTERN = "^(llm|ml_classifier|computer_vision|nlp|recommendation|generative|other)$"
AI_VENDOR_RISK_LEVEL_PATTERN = "^(low|medium|high|critical)$"


class AIVendorAssessmentCreate(BaseModel):
    ai_model_name: str | None = Field(default=None, max_length=255)
    ai_model_version: str | None = Field(default=None, max_length=100)
    ai_model_provider: str | None = Field(default=None, max_length=255)
    model_type: str | None = Field(default=None, pattern=AI_VENDOR_MODEL_TYPE_PATTERN)
    training_data_source: str | None = None
    training_data_governance: str | None = None
    data_exits_environment: bool | None = None
    data_exits_details: str | None = None
    bias_testing_performed: bool | None = None
    bias_testing_method: str | None = None
    bias_testing_frequency: str | None = Field(default=None, max_length=100)
    explainability_approach: str | None = None
    human_oversight_required: bool | None = None
    human_oversight_details: str | None = None
    output_used_for_decisions: bool | None = None
    decision_types: str | None = None
    regulatory_obligations: list[str] = Field(default_factory=list)
    vendor_ai_policy_url: str | None = Field(default=None, max_length=500)
    incident_history: str | None = None
    assessor_notes: str | None = None


class AIVendorAssessmentUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=AI_VENDOR_ASSESSMENT_STATUS_PATTERN)
    ai_model_name: str | None = Field(default=None, max_length=255)
    ai_model_version: str | None = Field(default=None, max_length=100)
    ai_model_provider: str | None = Field(default=None, max_length=255)
    model_type: str | None = Field(default=None, pattern=AI_VENDOR_MODEL_TYPE_PATTERN)
    training_data_source: str | None = None
    training_data_governance: str | None = None
    data_exits_environment: bool | None = None
    data_exits_details: str | None = None
    bias_testing_performed: bool | None = None
    bias_testing_method: str | None = None
    bias_testing_frequency: str | None = Field(default=None, max_length=100)
    explainability_approach: str | None = None
    human_oversight_required: bool | None = None
    human_oversight_details: str | None = None
    output_used_for_decisions: bool | None = None
    decision_types: str | None = None
    regulatory_obligations: list[str] | None = None
    vendor_ai_policy_url: str | None = Field(default=None, max_length=500)
    incident_history: str | None = None
    assessor_notes: str | None = None


class AIVendorAssessmentRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID
    assessor_id: UUID
    status: str = Field(pattern=AI_VENDOR_ASSESSMENT_STATUS_PATTERN)
    ai_model_name: str | None = None
    ai_model_version: str | None = None
    ai_model_provider: str | None = None
    model_type: str | None = Field(default=None, pattern=AI_VENDOR_MODEL_TYPE_PATTERN)
    training_data_source: str | None = None
    training_data_governance: str | None = None
    data_exits_environment: bool | None = None
    data_exits_details: str | None = None
    bias_testing_performed: bool | None = None
    bias_testing_method: str | None = None
    bias_testing_frequency: str | None = None
    explainability_approach: str | None = None
    human_oversight_required: bool | None = None
    human_oversight_details: str | None = None
    output_used_for_decisions: bool | None = None
    decision_types: str | None = None
    regulatory_obligations: list | dict
    vendor_ai_policy_url: str | None = None
    incident_history: str | None = None
    overall_risk_level: str | None = Field(default=None, pattern=AI_VENDOR_RISK_LEVEL_PATTERN)
    risk_score: int | None = None
    assessor_notes: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class AIVendorAssessmentSummary(BaseModel):
    total_assessments: int
    by_status: dict[str, int]
    by_risk_level: dict[str, int]
    by_model_type: dict[str, int]
    critical_count: int
    data_exits_count: int
    no_bias_testing_count: int
    no_human_oversight_decisions_count: int
