import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ThirdPartyAIAssessmentCreate(BaseModel):
    ai_system_id: uuid.UUID | None = None
    model_name: str = Field(min_length=1, max_length=255)
    model_version: str | None = Field(default=None, max_length=100)
    data_egress_type: str
    model_card_provided: bool = False
    bias_testing_documented: bool = False
    explainability_level: str | None = None
    contractual_ai_terms_reviewed: bool = False
    eu_act_compliance_status: str | None = None
    status: str = "draft"


class ThirdPartyAIAssessmentUpdate(BaseModel):
    ai_system_id: uuid.UUID | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=255)
    model_version: str | None = Field(default=None, max_length=100)
    data_egress_type: str | None = None
    model_card_provided: bool | None = None
    bias_testing_documented: bool | None = None
    explainability_level: str | None = None
    contractual_ai_terms_reviewed: bool | None = None
    eu_act_compliance_status: str | None = None
    status: str | None = None
    assessed_by: uuid.UUID | None = None


class ThirdPartyAIAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    vendor_id: uuid.UUID
    ai_system_id: uuid.UUID | None
    model_name: str
    model_version: str | None
    data_egress_type: str
    model_card_provided: bool
    bias_testing_documented: bool
    explainability_level: str | None
    contractual_ai_terms_reviewed: bool
    eu_act_compliance_status: str | None
    overall_risk_level: str | None
    status: str
    assessed_by: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ModelCardCreate(BaseModel):
    intended_purpose: str
    training_data_description: str | None = None
    training_data_cutoff_date: date | None = None
    known_limitations: list[str] = Field(default_factory=list)
    performance_metrics: dict = Field(default_factory=dict)
    approved_use_cases: list[str] = Field(default_factory=list)
    prohibited_use_cases: list[str] = Field(default_factory=list)
    bias_evaluation_results: str | None = None
    human_oversight_requirements: str | None = None
    contact_owner_id: uuid.UUID


class ModelCardUpdate(BaseModel):
    intended_purpose: str | None = None
    training_data_description: str | None = None
    training_data_cutoff_date: date | None = None
    known_limitations: list[str] | None = None
    performance_metrics: dict | None = None
    approved_use_cases: list[str] | None = None
    prohibited_use_cases: list[str] | None = None
    bias_evaluation_results: str | None = None
    human_oversight_requirements: str | None = None
    contact_owner_id: uuid.UUID | None = None


class ModelCardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    version: int
    intended_purpose: str
    training_data_description: str | None
    training_data_cutoff_date: date | None
    known_limitations: list[str]
    performance_metrics: dict
    approved_use_cases: list[str]
    prohibited_use_cases: list[str]
    bias_evaluation_results: str | None
    human_oversight_requirements: str | None
    content_hash: str | None
    contact_owner_id: uuid.UUID
    status: str
    published_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AIBOMComponentCreate(BaseModel):
    component_type: str
    name: str = Field(min_length=1, max_length=255)
    version: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=500)
    license_type: str | None = Field(default=None, max_length=100)
    is_third_party: bool = False
    risk_notes: str | None = None
    source_integration: str | None = Field(default=None, max_length=50)


class AIBOMCreateRequest(BaseModel):
    notes: str | None = None
    components: list[AIBOMComponentCreate] | None = None


class AIBOMComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    aibom_id: uuid.UUID
    component_type: str
    name: str
    version: str | None
    source: str | None
    license_type: str | None
    is_third_party: bool
    risk_notes: str | None
    source_integration: str | None
    created_at: datetime


class AIBOMRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    version: int
    generated_at: datetime
    generated_by: uuid.UUID
    notes: str | None


class AIBOMWithComponentsRead(BaseModel):
    record: AIBOMRecordRead
    components: list[AIBOMComponentRead]


class AIBOMDiffRead(BaseModel):
    added: list[dict]
    removed: list[dict]
    changed: list[dict]
