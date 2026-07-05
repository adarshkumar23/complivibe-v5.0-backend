from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PRIVACY_TECHNIQUES = ("differential_privacy", "k_anonymity", "none")
VALIDATION_STATUSES = ("unvalidated", "validated", "failed_validation")

PrivacyTechnique = Literal["differential_privacy", "k_anonymity", "none"]
ValidationStatus = Literal["unvalidated", "validated", "failed_validation"]


class SyntheticDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    generation_method: str = Field(min_length=1, max_length=255)
    source_dataset_id: UUID | None = None
    privacy_technique: PrivacyTechnique = "none"
    validation_status: ValidationStatus = "unvalidated"
    validation_notes: str | None = None


class SyntheticDatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    generation_method: str | None = Field(default=None, min_length=1, max_length=255)
    source_dataset_id: UUID | None = None
    privacy_technique: PrivacyTechnique | None = None
    validation_status: ValidationStatus | None = None
    validation_notes: str | None = None


class SyntheticDatasetValidateRequest(BaseModel):
    validation_status: ValidationStatus
    validation_notes: str | None = None


class SyntheticDatasetRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    generation_method: str
    source_dataset_id: UUID | None = None
    privacy_technique: str
    validation_status: str
    validation_notes: str | None = None
    governance_gap_flag: bool
    governance_gap_reason: str | None = None
    created_by: UUID | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
