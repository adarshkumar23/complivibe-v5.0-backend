import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConformityAssessmentCreate(BaseModel):
    assessment_type: str
    technical_documentation_complete: bool = False
    qms_compliant: bool = False
    human_oversight_measures: str | None = None
    accuracy_robustness_measures: str | None = None


class ConformityAssessmentUpdate(BaseModel):
    technical_documentation_complete: bool | None = None
    qms_compliant: bool | None = None
    human_oversight_measures: str | None = None
    accuracy_robustness_measures: str | None = None
    status: str | None = None


class ConformityChecklistItemCompleteRequest(BaseModel):
    item_key: str = Field(min_length=1)


class ConformityAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    assessment_type: str
    status: str
    technical_documentation_complete: bool
    qms_compliant: bool
    human_oversight_measures: str | None
    accuracy_robustness_measures: str | None
    checklist_items: list[dict[str, Any]]
    checklist_total_items: int = 0
    checklist_completed_items: int = 0
    checklist_completion_percent: float = 0
    missing_checklist_item_keys: list[str] = Field(default_factory=list)
    stale_workflow: bool = False
    context_flags: list[str] = Field(default_factory=list)
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class FRIACreate(BaseModel):
    rights_affected: list[str] = Field(default_factory=list)
    risk_to_rights_assessment: str | None = None
    mitigation_measures: str | None = None
    consultation_conducted: bool = False


class FRIAUpdate(BaseModel):
    rights_affected: list[str] | None = None
    risk_to_rights_assessment: str | None = None
    mitigation_measures: str | None = None
    consultation_conducted: bool | None = None
    status: str | None = None


class FRIARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    rights_affected: list[str]
    risk_to_rights_assessment: str | None
    mitigation_measures: str | None
    consultation_conducted: bool
    status: str
    rights_affected_count: int = 0
    completeness_percent: float = 0
    stale_workflow: bool = False
    context_flags: list[str] = Field(default_factory=list)
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PostMarketPlanCreate(BaseModel):
    monitoring_metrics: list[dict[str, Any]] | list[str] = Field(default_factory=list)
    reporting_frequency: str | None = None
    incident_reporting_threshold: str | None = None
    responsible_person_id: uuid.UUID


class PostMarketPlanUpdate(BaseModel):
    monitoring_metrics: list[dict[str, Any]] | list[str] | None = None
    reporting_frequency: str | None = None
    incident_reporting_threshold: str | None = None
    responsible_person_id: uuid.UUID | None = None
    status: str | None = None


class PostMarketPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    monitoring_metrics: list[dict[str, Any]] | list[str]
    reporting_frequency: str | None
    incident_reporting_threshold: str | None
    responsible_person_id: uuid.UUID
    status: str
    monitoring_metrics_count: int = 0
    completeness_percent: float = 0
    stale_workflow: bool = False
    context_flags: list[str] = Field(default_factory=list)
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
